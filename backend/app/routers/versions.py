"""Saved versions of a filtered run, their export, and the Analysis step."""

import io
import json
from collections import Counter

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import ApiCall, Run, Version
from app.routers.scout import _run_out, kw_stats
from app.services import records
from app.services.analysis import points, profile
from app.services.storage import Storage
from app.services.summary import summarize
from app.settings import get_settings

router = APIRouter(prefix="/api/versions", tags=["versions"], dependencies=[Depends(current_user)])

EXPORT_COLS = ["place_id", "name", "address", "area_jp", "area_en", "type_label", "type_label_jp", "status", "rating", "reviews",
               "pay", "phone", "web", "photos", "lat", "lng", "hex_id", "maps_uri", "keywords", "chain"]


class NewVersion(BaseModel):
    run_id: int
    name: str
    notes: str = ""
    filters: dict = {}


class Combine(BaseModel):
    version_ids: list[int]
    name: str = ""
    notes: str = ""
    dry_run: bool = False


def _run_ids(v: Version) -> list[int]:
    return v.sources["runs"] if v.sources else [v.run_id]


def _out(v: Version, prev_rows: int | None, runs: list[Run], names: dict[int, str] | None = None) -> dict:
    s = get_settings()
    areas = {(a["city"], a["area"]) for r in runs for a in r.areas}
    return {"id": v.id, "name": v.name, "notes": v.notes, "author": v.author, "created_at": v.created_at,
            "run_id": v.run_id, "rows": v.rows, "diff": None if prev_rows is None else v.rows - prev_rows,
            "cities": sorted({c for c, _ in areas}), "areas": len(areas),
            "keywords": len({k for r in runs for k in r.keywords}),
            "mock": any(r.mock for r in runs), "cost_local": round(sum(r.cost_usd for r in runs) * s.usd_rate, 2),
            "export_uri": v.export_uri, "analyzed": v.analysis is not None,
            "sources": [{"id": i, "name": (names or {}).get(i, f"#{i}")} for i in v.sources["versions"]] if v.sources else None}


@router.get("")
def list_versions(db: Session = Depends(get_db)):
    vs = db.scalars(select(Version).order_by(Version.id)).all()
    runs = {r.id: r for r in db.scalars(select(Run).where(Run.id.in_({i for v in vs for i in _run_ids(v)})))}
    names = {v.id: v.name for v in vs}
    out, prev = [], None
    for v in vs:
        out.append(_out(v, prev, [runs[i] for i in _run_ids(v)], names))
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
    return _out(v, prev, [run])


@router.post("/combine")
def combine(body: Combine, db: Session = Depends(get_db), user: str = Depends(current_user)):
    """A new version holding every place of the chosen versions once. The sources are left as they are.
    A place found by several versions keeps its row from the newest run (the freshest Google data)."""
    ids = list(dict.fromkeys(body.version_ids))
    if len(ids) < 2:
        raise HTTPException(422, "Pick at least two versions to combine")
    srcs = db.scalars(select(Version).where(Version.id.in_(ids))).all()
    if len(srcs) != len(ids):
        _404()
    run_ids = sorted({i for v in srcs for i in _run_ids(v)})
    df = _frames(run_ids)
    df = df[df["pk"].isin({pk for v in srcs for pk in v.place_ids})] if not df.empty else df
    rows_in = sum(v.rows for v in srcs)
    kept = df.sort_values("run_id", ascending=False).drop_duplicates("place_id") if not df.empty else df
    stats = {"rows_in": rows_in, "rows": len(kept), "duplicates": rows_in - len(kept)}
    if body.dry_run:
        return stats
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Give the combined version a name")
    if db.scalar(select(Version.id).where(Version.name == name)):
        raise HTTPException(409, "A version with this name exists")
    by_id = {v.id: v for v in srcs}
    v = Version(run_id=max(run_ids), name=name, notes=body.notes, author=user,
                filters={"combined": [by_id[i].name for i in ids]}, place_ids=[int(x) for x in kept["pk"]],
                rows=len(kept), sources={"versions": ids, "runs": run_ids})
    db.add(v)
    db.flush()
    try:
        v.export_uri = Storage().put_csv(f"versions/{v.name}.csv", _export_frame(kept))
    except Exception as e:  # noqa: BLE001  the DB copy is enough to keep working
        v.export_uri = f"upload failed: {e}"
    db.commit()
    prev = db.scalar(select(Version.rows).where(Version.id < v.id).order_by(Version.id.desc()).limit(1))
    runs = db.scalars(select(Run).where(Run.id.in_(run_ids))).all()
    return _out(v, prev, list(runs), {s.id: s.name for s in srcs}) | stats


@router.get("/{version_id}/export.csv")
def export(version_id: int, db: Session = Depends(get_db)):
    v = db.get(Version, version_id) or _404()
    df = _version_frame(v)
    buf = io.StringIO()
    _export_frame(df).to_csv(buf, index=False)
    return StreamingResponse(iter([buf.getvalue().encode("utf-8-sig")]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{v.name}.csv"'})


@router.get("/{version_id}/points")
def version_points(version_id: int, db: Session = Depends(get_db)):
    v = db.get(Version, version_id) or _404()
    return points(_version_frame(v))


@router.get("/{version_id}/analysis")
def get_analysis(version_id: int, db: Session = Depends(get_db)):
    v = db.get(Version, version_id) or _404()
    return v.analysis or {}


@router.post("/{version_id}/analyze")
def analyze(version_id: int, db: Session = Depends(get_db)):
    v = db.get(Version, version_id) or _404()
    run = db.get(Run, v.run_id)
    run_info, stats = _context(db, v)
    p = profile(_version_frame(v), run_info, stats)
    if p["rows"] == 0:
        raise HTTPException(422, "This version has no rows")
    p = json.loads(json.dumps(p, default=str))  # plain JSON for the DB column
    try:
        summary, call = summarize(p, mock=run_info["mock"])
    except Exception as e:  # noqa: BLE001  charts are still useful without the narrative
        from app.services.summary import rule_based

        summary = rule_based(p) | {"source": f"rules (Vertex error: {type(e).__name__})"}
        call = {"mock": False, "status": f"ERROR:{type(e).__name__}", "tokens_in": 0, "tokens_out": 0,
                "latency_ms": 0, "cost_usd": 0.0}
    db.add(ApiCall(version_id=v.id, run_id=run.id, api=get_settings().llm_api, sku=get_settings().llm_model,
                   mock=call["mock"], status=call["status"], latency_ms=call["latency_ms"],
                   cost_usd=call["cost_usd"], tokens_in=call["tokens_in"], tokens_out=call["tokens_out"]))
    v.analysis = {"profile": p, "summary": summary}
    db.commit()
    return v.analysis


def _frames(run_ids: list[int]) -> pd.DataFrame:
    parts = [records.frame(i).assign(run_id=i) for i in run_ids]
    parts = [d for d in parts if not d.empty]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _version_frame(v: Version) -> pd.DataFrame:
    df = _frames(_run_ids(v))
    return df[df["pk"].isin(set(v.place_ids))] if not df.empty else df


def _context(db: Session, v: Version) -> tuple[dict, dict]:
    """The run summary and keyword stats the profile reads. For a combined version: every source run
    merged, with unique places counted once across runs."""
    runs = [db.get(Run, i) for i in _run_ids(v)]
    if len(runs) == 1:
        return _run_out(runs[0]), kw_stats(db, runs[0].id)
    outs = [_run_out(r) for r in runs]
    areas = list({(a["city"], a["area"]): a for o in outs for a in o["areas"]}.values())
    merged = outs[-1] | {k: sum(o[k] for o in outs) for k in
                         ("total_tasks", "done_tasks", "raw_hits", "saturated", "splits", "api_calls", "cost_usd", "cost_local")}
    merged |= {"keywords": list(dict.fromkeys(k for o in outs for k in o["keywords"])), "areas": areas,
               "mock": any(o["mock"] for o in outs), "base_res": min(o["base_res"] for o in outs),
               "max_res": max(o["max_res"] for o in outs), "run_ids": [o["id"] for o in outs]}
    every = _frames(_run_ids(v)).drop_duplicates("place_id")
    merged["unique_places"] = len(every)
    merged["dupes"] = merged["raw_hits"] - merged["unique_places"]
    unique = Counter(k for kws in every["keywords"] for k in kws)
    stats: dict[str, dict] = {}
    for r in runs:
        for k, st in kw_stats(db, r.id).items():
            acc = stats.setdefault(k, {"calls": 0, "searches": 0, "empty": 0, "hits": 0})
            for f in acc:
                acc[f] += st[f]
    return merged, {k: st | {"unique": unique[k]} for k, st in stats.items()}


def _export_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df[EXPORT_COLS].copy()
    out["keywords"] = out["keywords"].map("|".join)
    out["pay"] = out["pay"].map(records.PAY)
    return out


def _404():
    raise HTTPException(404, "Not found")
