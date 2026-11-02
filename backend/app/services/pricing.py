"""Cost per call and the pre-run estimate."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Run
from app.settings import get_settings

PLACES_SKU = "Text Search Enterprise + Atmosphere"

# Fallback calls per base cell x keyword (pages + split children) before any run history exists,
# from the first Osaka runs: dense res-8 cells page 3x and split; suburbs return a single page.
DEFAULT_CALLS_PER_TASK = {7: 6.0, 8: 2.6, 9: 1.5, 10: 1.15, 11: 1.05}


def places_call_usd() -> float:
    return get_settings().places_usd_per_1000 / 1000


def claude_usd(tokens_in: int, tokens_out: int) -> float:
    s = get_settings()
    return tokens_in / 1e6 * s.claude_usd_per_mtok_in + tokens_out / 1e6 * s.claude_usd_per_mtok_out


def calls_per_task(db: Session, base_res: int, max_res: int) -> tuple[float, str]:
    """Average calls per base task from finished runs with the same grid settings, else the default."""
    row = db.execute(
        select(func.sum(Run.api_calls), func.sum(Run.total_tasks - Run.splits * 7))
        .where(Run.status == "done", Run.base_res == base_res, Run.max_res == max_res)
    ).one()
    calls, base_tasks = row
    if calls and base_tasks and base_tasks > 0:
        return calls / base_tasks, "history"
    return DEFAULT_CALLS_PER_TASK.get(base_res, 2.0) * (1 + 0.15 * max(0, max_res - base_res - 1)), "default"


def estimate(db: Session, cells: int, keywords: int, base_res: int, max_res: int) -> dict:
    s = get_settings()
    tasks = cells * keywords
    per_task, source = calls_per_task(db, base_res, max_res)
    expected = round(tasks * per_task)
    usd = expected * places_call_usd()
    return {
        "cells": cells, "keywords": keywords, "tasks": tasks,
        "min_calls": tasks, "expected_calls": expected, "calls_per_task": round(per_task, 2), "basis": source,
        "expected_usd": round(usd, 2), "expected_local": round(usd * s.usd_rate, 2),
        "min_local": round(tasks * places_call_usd() * s.usd_rate, 2),
        "usd_per_call": places_call_usd(), "sku": PLACES_SKU,
    }
