"""API spend from the api_calls ledger. The header meter is open; the breakdown needs the passcode."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import billing_access, check_passcode, current_user, issue_billing_token
from app.db import get_db
from app.models import ApiCall
from app.settings import get_settings

router = APIRouter(prefix="/api/billing", tags=["billing"])

JST = timezone(timedelta(hours=9))


def _month_start() -> datetime:
    now = datetime.now(JST)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@router.get("/meter")
def meter(db: Session = Depends(get_db), _: str = Depends(current_user)):
    s = get_settings()
    start = _month_start()
    usd = db.scalar(select(func.coalesce(func.sum(ApiCall.cost_usd), 0.0))
                    .where(ApiCall.mock.is_(False), ApiCall.ts >= start)) or 0.0
    return {"month": start.strftime("%b"), "spent_local": round(usd * s.usd_rate, 2), "budget": s.monthly_budget, "currency": s.currency}


class Unlock(BaseModel):
    passcode: str


@router.post("/unlock")
def unlock(body: Unlock, user: str = Depends(current_user)):
    if not check_passcode(body.passcode):
        raise HTTPException(403, "Wrong passcode")
    return {"token": issue_billing_token(user)}


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: str = Depends(billing_access)):
    s = get_settings()
    rate = s.usd_rate
    start = _month_start()

    def agg(*group, where=()):
        q = select(*group, func.count(), func.sum(ApiCall.cost_usd), func.avg(ApiCall.latency_ms)).where(*where)
        if group:
            q = q.group_by(*group).order_by(*group)
        return db.execute(q).all()

    total = {mock: {"calls": n, "usd": round(usd or 0, 4), "local": round((usd or 0) * rate, 2)}
             for mock, n, usd, _ in agg(ApiCall.mock)}
    month = {mock: {"calls": n, "usd": round(usd or 0, 4), "local": round((usd or 0) * rate, 2)}
             for mock, n, usd, _ in agg(ApiCall.mock, where=(ApiCall.ts >= start,))}
    by_sku = [{"api": api, "sku": sku, "mock": mock, "calls": n, "usd": round(usd or 0, 4),
               "local": round((usd or 0) * rate, 2), "avg_ms": round(ms or 0)}
              for api, sku, mock, n, usd, ms in agg(ApiCall.api, ApiCall.sku, ApiCall.mock)]
    by_run = [{"run_id": rid, "mock": mock, "calls": n, "usd": round(usd or 0, 4), "local": round((usd or 0) * rate, 2)}
              for rid, mock, n, usd, _ in agg(ApiCall.run_id, ApiCall.mock)]
    day = func.date(ApiCall.ts)
    by_day = [{"day": str(d), "mock": mock, "calls": n, "local": round((usd or 0) * rate, 2)}
              for d, mock, n, usd, _ in agg(day, ApiCall.mock, where=(ApiCall.ts >= start - timedelta(days=31),))]
    errors = db.scalar(select(func.count()).select_from(ApiCall).where(ApiCall.status != "OK",
                                                                       ApiCall.status != "end_turn"))
    return {
        "budget": s.monthly_budget, "usd_rate": rate, "currency": s.currency, "month": start.strftime("%Y-%m"),
        "real_month": month.get(False, {"calls": 0, "usd": 0, "local": 0}),
        "mock_month": month.get(True, {"calls": 0, "usd": 0, "local": 0}),
        "real_total": total.get(False, {"calls": 0, "usd": 0, "local": 0}),
        "mock_total": total.get(True, {"calls": 0, "usd": 0, "local": 0}),
        "by_sku": by_sku, "by_run": list(reversed(by_run)), "by_day": by_day, "errors": errors,
        "pricing": {"places_usd_per_1000": s.places_usd_per_1000, "field_mask": s.places_field_mask,
                    "claude_model": s.claude_model, "claude_usd_per_mtok": [s.claude_usd_per_mtok_in,
                                                                            s.claude_usd_per_mtok_out]},
    }


@router.get("/calls")
def calls(limit: int = 100, offset: int = 0, run_id: int | None = None, api: str | None = None,
          mock: bool | None = None, db: Session = Depends(get_db), _: str = Depends(billing_access)):
    rate = get_settings().usd_rate
    q = select(ApiCall)
    if run_id is not None:
        q = q.where(ApiCall.run_id == run_id)
    if api:
        q = q.where(ApiCall.api == api)
    if mock is not None:
        q = q.where(ApiCall.mock.is_(mock))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(ApiCall.id.desc()).offset(offset).limit(min(limit, 500))).all()
    return {"total": total, "rows": [
        {"id": c.id, "ts": c.ts, "run_id": c.run_id, "version_id": c.version_id, "api": c.api, "sku": c.sku,
         "mock": c.mock, "status": c.status, "ms": c.latency_ms, "usd": c.cost_usd, "local": round(c.cost_usd * rate, 2),
         "hex": c.hex_id, "res": c.res, "keyword": c.keyword, "page": c.page, "results": c.results,
         "tokens_in": c.tokens_in, "tokens_out": c.tokens_out} for c in rows]}
