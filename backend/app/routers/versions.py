"""Saved versions of a filtered run, their export, and the Analysis step."""

import io
import json

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import ApiCall, Run, Version
from app.routers.scout import _run_out, kw_calls
from app.services import records
from app.services.analysis import profile
from app.services.storage import Storage
from app.services.summary import summarize
from app.settings import get_settings

router = APIRouter(prefix="/api/versions", tags=["versions"], dependencies=[Depends(current_user)])

EXPORT_COLS = ["place_id", "name", "address", "area_jp", "area_en", "type_label", "status", "rating", "reviews",
               "pay", "phone", "web", "photos", "lat", "lng", "hex_id", "maps_uri", "keywords", "chain"]


class NewVersion(BaseModel):
    run_id: int
    name: str
    notes: str = ""
    filters: dict = {}


def _out(v: Version, prev_rows: int | None, run: Run) -> dict:
    s = get_settings()
    return {"id": v.id, "name": v.name, "notes": v.notes, "author": v.author, "created_at": v.created_at,
            "run_id": v.run_id, "rows": v.rows, "diff": None if prev_rows is None else v.rows - prev_rows,
            "cities": sorted({a["city"] for a in run.areas}), "areas": len(run.areas), "keywords": len(run.keywords),
            "mock": run.mock, "cost_local": round(run.cost_usd * s.usd_rate, 2), "export_uri": v.export_uri,
            "analyzed": v.analysis is not None}


@router.get("")
def list_versions(db: Session = Depends(get_db)):
    vs = db.scalars(select(Version).order_by(Version.id)).all()
    runs = {r.id: r for r in db.scalars(select(Run).where(Run.id.in_({v.run_id for v in vs})))}
    out, prev = [], None
    for v in vs:
        out.append(_out(v, prev, runs[v.run_id]))
        prev = v.rows
    return list(reversed(out))


@router.get("/next-name")
def next_name(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id) or _404()
    city = (run.areas[0]["city"].split("-")[0] if run.areas else "x")
    n = len(db.scalars(select(Version.id)).all()) + 1
    return {"name": f"{city}-fnb_{run.created_at:%Y-%m-%d}_v{n}"}


@router.post("")
def save_version(body: NewVersion, db: Session = Depends(get_db), user: str = Depends(current_user)):
    run = db.get(Run, body.run_id) or _404()
    if run.status != "done":
        raise HTTPException(409, "The run has not finished")
    if db.scalar(select(Version.id).where(Version.name == body.name)):
        raise HTTPException(409, "A version with this name exists")
    df = records.frame(run.id)
    f = records.default_filters(df) | body.filters
    kept, _ = records.apply(df, f)
    v = Version(run_id=run.id, name=body.name.strip(), notes=body.notes, author=user, filters=f,
                place_ids=[int(x) for x in kept["pk"]], rows=len(kept))
    db.add(v)
    db.flush()
    try:
        v.export_uri = Storage().put_csv(f"versions/{v.name}.csv", _export_frame(kept))
    except Exception as e:  # noqa: BLE001  the DB copy is enough to keep working
        v.export_uri = f"upload failed: {e}"
    db.commit()
    prev = db.scalar(select(Version.rows).where(Version.id < v.id).order_by(Version.id.desc()).limit(1))
    return _out(v, prev, run)


@router.get("/{version_id}/export.csv")
def export(version_id: int, db: Session = Depends(get_db)):
    v = db.get(Version, version_id) or _404()
    df = _version_frame(v)
    buf = io.StringIO()
    _export_frame(df).to_csv(buf, index=False)
    return StreamingResponse(iter([buf.getvalue().encode("utf-8-sig")]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{v.name}.csv"'})


@router.get("/{version_id}/analysis")
def get_analysis(version_id: int, db: Session = Depends(get_db)):
    v = db.get(Version, version_id) or _404()
    return v.analysis or {}


@router.post("/{version_id}/analyze")
def analyze(version_id: int, db: Session = Depends(get_db)):
    v = db.get(Version, version_id) or _404()
    run = db.get(Run, v.run_id)
    p = profile(_version_frame(v), _run_out(run), kw_calls(db, run.id))
    if p["rows"] == 0:
        raise HTTPException(422, "This version has no rows")
    p = json.loads(json.dumps(p, default=str))  # plain JSON for the DB column
    try:
        summary, call = summarize(p, mock=run.mock)
    except Exception as e:  # noqa: BLE001  charts are still useful without the narrative
        from app.services.summary import rule_based

        summary = rule_based(p) | {"source": f"rules (Vertex error: {type(e).__name__})"}
        call = {"mock": False, "status": f"ERROR:{type(e).__name__}", "tokens_in": 0, "tokens_out": 0,
                "latency_ms": 0, "cost_usd": 0.0}
    db.add(ApiCall(version_id=v.id, run_id=run.id, api="vertex.claude", sku=get_settings().claude_model,
                   mock=call["mock"], status=call["status"], latency_ms=call["latency_ms"],
                   cost_usd=call["cost_usd"], tokens_in=call["tokens_in"], tokens_out=call["tokens_out"]))
    v.analysis = {"profile": p, "summary": summary}
    db.commit()
    return v.analysis


def _version_frame(v: Version) -> pd.DataFrame:
    df = records.frame(v.run_id)
    return df[df["pk"].isin(set(v.place_ids))] if not df.empty else df


def _export_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df[EXPORT_COLS].copy()
    out["keywords"] = out["keywords"].map("|".join)
    out["pay"] = out["pay"].map(records.PAY)
    return out


def _404():
    raise HTTPException(404, "Not found")
