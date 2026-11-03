"""Scout: define a retrieval, run it, filter the result."""

from collections import Counter
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import ApiCall, Place, Run, RunCell, RunLog
from app.services import executor, keywords, pricing, records, regions
from app.services.analysis import points, profile
from app.services.collector import log, queue_run
from app.settings import get_settings

router = APIRouter(prefix="/api", tags=["scout"], dependencies=[Depends(current_user)])

RES_RANGE = (7, 11)
JST = timezone(timedelta(hours=9))


class AreaRef(BaseModel):
    city: str
    area: str


class Plan(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    areas: list[AreaRef] = Field(default_factory=list)
    base_res: int = 8
    max_res: int = 10


class NewRun(Plan):
    mock: bool = True


def _validate(plan: Plan) -> None:
    if not RES_RANGE[0] <= plan.base_res <= RES_RANGE[1] - 1:
        raise HTTPException(422, f"Base resolution must be {RES_RANGE[0]}–{RES_RANGE[1] - 1}")
    if not plan.base_res <= plan.max_res <= RES_RANGE[1]:
        raise HTTPException(422, "Max split resolution must be at least the base resolution")


@router.get("/scout/config")
def config():
    s = get_settings()
    return {"keywords": keywords.catalogue(), "default_mock": s.default_mock, "res_range": RES_RANGE,
            "usd_rate": s.usd_rate, "currency": s.currency, "sku": pricing.PLACES_SKU, "usd_per_call": pricing.places_call_usd(),
            "has_maps_key": bool(s.maps_api_key)}


@router.get("/scout/cities")
def cities():
    return regions.cities()


@router.get("/scout/cities/{city}/areas")
def city_areas(city: str, res: int = 8):
    try:
        return regions.city_areas(city, res)
    except KeyError:
        raise HTTPException(404, "Unknown city")


@router.post("/scout/geometry")
def geometry(codes: list[str]):
    return regions.area_geojson(codes)


@router.post("/scout/estimate")
def estimate(plan: Plan, db: Session = Depends(get_db)):
    _validate(plan)
    codes = [a.area for a in plan.areas]
    cells = len(regions.selection_hexes(codes, plan.base_res)) if codes else 0
    est = pricing.estimate(db, cells, len(plan.keywords), plan.base_res, plan.max_res)
    est["by_res"] = [{"res": r, "km2": regions.H3_AREA_KM2[r],
                      "cells": len(regions.selection_hexes(codes, r)) if codes and r <= 10 else None}
                     for r in range(7, 11)]
    return est


@router.post("/runs")
def create_run(body: NewRun, db: Session = Depends(get_db), user: str = Depends(current_user)):
    _validate(body)
    kws = list(dict.fromkeys(k.strip() for k in body.keywords if k.strip()))
    if not kws or not body.areas:
        raise HTTPException(422, "Pick at least one keyword and one area")
    if not body.mock and not get_settings().maps_api_key:
        raise HTTPException(422, "No Google Maps API key configured; use Mock")
    if db.scalar(select(func.count()).select_from(Run).where(Run.status.in_(("queued", "running", "cancelling")))):
        raise HTTPException(409, "Another run is still in progress")
    run = Run(author=user, mock=body.mock, keywords=kws, areas=[a.model_dump() for a in body.areas],
              base_res=body.base_res, max_res=body.max_res)
    db.add(run)
    db.flush()
    cells = len(regions.selection_hexes([a.area for a in body.areas], body.base_res))
    run.estimate = pricing.estimate(db, cells, len(kws), body.base_res, body.max_res)
    queue_run(db, run)
    db.commit()
    mode = executor.start(run.id)
    return {"id": run.id, "mode": mode}


def _run_out(run: Run) -> dict:
    return {
        "id": run.id, "status": run.status, "mock": run.mock, "error": run.error, "author": run.author,
        "created_at": run.created_at, "finished_at": run.finished_at, "keywords": run.keywords,
        "areas": run.areas, "base_res": run.base_res, "max_res": run.max_res,
        "total_tasks": run.total_tasks, "done_tasks": run.done_tasks, "raw_hits": run.raw_hits,
        "unique_places": run.unique_places, "dupes": run.raw_hits - run.unique_places,
        "saturated": run.saturated, "splits": run.splits, "api_calls": run.api_calls,
        "cost_usd": round(run.cost_usd, 4), "cost_local": round(run.cost_usd * get_settings().usd_rate, 2),
        "estimate": run.estimate,
    }


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)):
    return [_run_out(r) for r in db.scalars(select(Run).order_by(Run.id.desc()).limit(50))]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id) or _404()
    logs = db.scalars(select(RunLog).where(RunLog.run_id == run_id, RunLog.level != "debug")
                      .order_by(RunLog.id.desc()).limit(14)).all()
    # Progress per area x keyword, counting split children as part of their base task
    per_area = db.execute(select(RunCell.area, RunCell.status, func.count()).where(RunCell.run_id == run_id)
                          .group_by(RunCell.area, RunCell.status)).all()
    areas: dict[str, Counter] = {}
    for area, status, n in per_area:
        areas.setdefault(area, Counter())[status] += n
    out = _run_out(run)
    out["logs"] = [{"t": l.ts, "level": l.level, "m": l.message} for l in reversed(logs)]
    out["area_progress"] = [
        {"area": a, "jp": regions.area(a)["jp"], "en": regions.area(a)["en"],
         "done": c["done"] + c["split"] + c["saturated"] + c["error"], "total": sum(c.values())}
        for a, c in sorted(areas.items())]
    return out


@router.get("/runs/{run_id}/cells")
def run_cells(run_id: int, db: Session = Depends(get_db)):
    """Per-hex state across keywords for the live map: active > queued > done."""
    rows = db.execute(select(RunCell.hex_id, RunCell.status, RunCell.results).where(RunCell.run_id == run_id)).all()
    state: dict[str, dict] = {}
    rank = {"active": 3, "queued": 2, "done": 1, "split": 1, "saturated": 1, "error": 1}
    for hx, status, results in rows:
        s = state.setdefault(hx, {"h": hx, "s": "done", "n": 0, "sat": False, "_r": 0})
        if rank[status] > s["_r"]:
            s["s"], s["_r"] = ("done" if rank[status] == 1 else status), rank[status]
        s["n"] = max(s["n"], results)
        s["sat"] = s["sat"] or status == "saturated"
    return [{k: v for k, v in s.items() if k != "_r"} for s in state.values()]


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id) or _404()
    # Queued: the job hasn't picked it up, so stop it now. Cancelling again: force-stop a run whose job died.
    if run.status in ("queued", "cancelling"):
        forced = run.status == "cancelling"
        run.status, run.finished_at = "cancelled", datetime.now(timezone.utc)
        log(db, run.id, "force-stopped by user" if forced else "cancelled before start", "warn")
        db.commit()
    elif run.status == "running":
        run.status = "cancelling"
        db.commit()
    return {"status": run.status}


# Preview sort keys → (column, ascending by default). Missing values always sort last.
PREVIEW_SORT = {"reviews": ("reviews", False), "rating": ("rating", False), "name": ("name", True),
                "area": ("area_en", True), "type": ("type_label", True), "price": ("price", True),
                "pay": ("pay_rank", True), "contact": ("contact", False)}
PAY_RANK = {"cash": 0, "none": 1, "card": 2, "nfc": 3}


def _sorted_preview(kept: pd.DataFrame, sort: str, desc: bool | None, n: int) -> list[dict]:
    col, asc = PREVIEW_SORT.get(sort, PREVIEW_SORT["reviews"])
    if desc is not None:
        asc = not desc
    d = kept.assign(
        pay_rank=kept["pay"].map(PAY_RANK),
        contact=kept["phone"].notna().astype(int) + kept["web"].notna().astype(int),
        # band 5 is "unknown price": treat as missing so it sorts last
        price=kept["price"].where(kept["price"] < 5),
    )
    # Ties fall back to most reviewed
    d = d.sort_values([col, "reviews"], ascending=[asc, False], na_position="last", kind="stable")
    return [_preview_row(r) for _, r in kept.loc[d.index[:n]].iterrows()]


@router.post("/runs/{run_id}/filter")
def filter_run(run_id: int, filters: dict | None = None, preview: int = 40, sort: str = "reviews",
               desc: bool | None = None, db: Session = Depends(get_db)):
    db.get(Run, run_id) or _404()
    df = records.frame(run_id)
    if df.empty:
        return {"total": 0, "count": 0, "funnel": [], "options": {}, "preview": [], "filters": {}}
    f = records.default_filters(df) | (filters or {})
    kept, funnel = records.apply(df, f)
    return {
        "total": len(df), "count": len(kept), "funnel": funnel, "filters": f,
        "defaults": records.default_filters(df),
        "options": _options(df),
        "sort": sort if sort in PREVIEW_SORT else "reviews",
        "preview": _sorted_preview(kept, sort, desc, preview),
    }


@router.post("/runs/{run_id}/result")
def run_result(run_id: int, filters: dict | None = None, db: Session = Depends(get_db)):
    """Stats for the Summary step: the filtered set before it is saved as a version."""
    run = db.get(Run, run_id) or _404()
    df = records.frame(run_id)
    f = records.default_filters(df) | (filters or {})
    kept, _ = records.apply(df, f) if not df.empty else (df, [])
    if kept.empty:
        return {"count": 0}
    p = profile(kept, _run_out(run), kw_stats(db, run_id))
    city_of = {a["area"]: a["city"] for a in run.areas}
    cities = []
    for c, g in kept.groupby(kept["area"].map(lambda a: city_of.get(a, "outside"))):
        cities.append({"city": c, "places": len(g),
                       "cash_or_unknown_pct": round(100 * g["pay"].isin(["cash", "none"]).mean(), 1),
                       "median_rating": _med(g["rating"]), "median_reviews": _med(g["reviews"])})
    return {"count": len(kept), "profile": p, "cities": cities, "run": _run_out(run)}


@router.post("/runs/{run_id}/points")
def run_points(run_id: int, filters: dict | None = None, db: Session = Depends(get_db)):
    """Every merchant in the filtered set, for the interactive map."""
    db.get(Run, run_id) or _404()
    df = records.frame(run_id)
    kept, _ = records.apply(df, records.default_filters(df) | (filters or {})) if not df.empty else (df, [])
    return points(kept)


def kw_stats(db: Session, run_id: int) -> dict[str, dict]:
    """Per keyword from the call ledger and the run's places, before any filter:
    calls (pages included), searches (cell × term), empty searches, raw hits and unique places."""
    rows = db.execute(
        select(ApiCall.keyword, func.count(), func.sum(case((ApiCall.page == 1, 1), else_=0)),
               func.sum(case(((ApiCall.page == 1) & (ApiCall.results == 0), 1), else_=0)), func.sum(ApiCall.results))
        .where(ApiCall.run_id == run_id, ApiCall.api == "places.searchText").group_by(ApiCall.keyword)).all()
    unique = Counter(k for kws in db.scalars(select(Place.keywords).where(Place.run_id == run_id)) for k in kws)
    return {k: {"calls": n, "searches": int(s or 0), "empty": int(e or 0), "hits": int(h or 0), "unique": unique[k]}
            for k, n, s, e, h in rows if k}


def _med(s: pd.Series):
    s = s.dropna()
    return float(s.median()) if len(s) else None


def _options(df) -> dict:
    vc = lambda col: {str(k): int(v) for k, v in df[col].value_counts().items()}  # noqa: E731
    types = df.groupby(["type", "type_label"]).size().sort_values(ascending=False)
    return {
        "status": [{"k": k, "l": l, "n": int((df["status"] == k).sum())} for k, l in records.STATUS.items()],
        "fnb": [{"k": k, "l": l, "n": int((df["fnb"] == k).sum())} for k, l in records.FNB_LABEL.items()],
        "price": [{"k": i, "l": l, "n": int((df["price"] == i).sum())} for i, l in enumerate(records.PRICE_BANDS)],
        "pay": [{"k": k, "l": l, "n": int((df["pay"] == k).sum())} for k, l in records.PAY.items()],
        "types": [{"k": t, "l": l, "n": int(n)} for (t, l), n in types.head(16).items()],
        "svc": [{"k": k, "l": l, "n": int(df[k].fillna(False).astype(bool).sum())} for k, l in records.SERVICES.items()],
        "qual": [{"k": "phone", "l": records.QUALITY["phone"], "n": int(df["phone"].notna().sum())},
                 {"k": "web", "l": records.QUALITY["web"], "n": int(df["web"].notna().sum())},
                 {"k": "photos", "l": records.QUALITY["photos"], "n": int((df["photos"] >= 5).sum())},
                 {"k": "nochain", "l": records.QUALITY["nochain"], "n": int((~df["chain"]).sum())}],
        "areas": [{"k": a, "l": g["area_en"].iloc[0], "jp": g["area_jp"].iloc[0], "n": len(g)}
                  for a, g in df.groupby("area")],
        "rating_hist": [int(((df["rating"] >= lo) & (df["rating"] < lo + 0.3)).sum())
                        for lo in [2.0, 2.3, 2.6, 2.9, 3.2, 3.5, 3.8, 4.1, 4.4, 4.7]],
        "review_hist": [int(((df["reviews"].fillna(0) >= lo) & (df["reviews"].fillna(0) < hi)).sum())
                        for lo, hi in zip(records.REVIEW_STEPS, records.REVIEW_STEPS[1:] + [10 ** 9])],
        "unrated": int(df["rating"].isna().sum()),
        "no_hours": int((~df["has_hours"]).sum()),
        "review_steps": records.REVIEW_STEPS,
        "status_counts": vc("status"),
    }


def _preview_row(r) -> dict:
    today = (datetime.now(JST).weekday() + 1) % 7  # Google weeks start on Sunday
    # Minutes from today's midnight; Japanese listings write past-midnight closes as 25:00 etc.
    spans = [(s - today * 1440, e - today * 1440) for s, e in r["hours"] if s // 1440 == today]
    fmt = lambda m: f"{m // 60:02d}:{m % 60:02d}"  # noqa: E731
    hours = ", ".join(f"{fmt(s)}–{fmt(e)}" for s, e in spans) if spans else ("closed" if r["has_hours"] else "—")
    return {"pk": int(r["pk"]), "name": r["name"], "area": r["area_en"], "type": r["type_label"],
            "rating": None if pd.isna(r["rating"]) else r["rating"],
            "reviews": None if pd.isna(r["reviews"]) else int(r["reviews"]),
            "price": records.PRICE_BANDS[int(r["price"])], "pay": r["pay"], "pay_label": records.PAY[r["pay"]],
            "today": hours, "maps_uri": r["maps_uri"], "status": r["status"],
            "phone": r["phone"] if pd.notna(r["phone"]) else None, "web": r["web"] if pd.notna(r["web"]) else None}


def _404():
    raise HTTPException(404, "Not found")
