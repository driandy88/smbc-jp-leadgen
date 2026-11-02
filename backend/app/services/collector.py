"""Hex-by-hex Text Search with recursive splitting, recorded to the database.

Same algorithm as DataCollectionPipeline.retrieve_google_maps_doors: search the cell's bounding
box, page through up to 60 results, and when a cell comes back full, search its 7 children
instead. Differences: work is queued in run_cells so the UI can show progress and a run can be
cancelled, every call is logged to api_calls, and places are de-duplicated by place id as they
arrive rather than in a post-processing step.
"""

import logging
import traceback
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import ApiCall, Place, Run, RunCell, RunLog
from app.services import regions
from app.services.places_client import MockPlaces, RealPlaces
from app.services.pricing import PLACES_SKU, places_call_usd
from app.services.storage import Storage, run_prefix
from app.settings import get_settings
from modules.h3_hexagon.hexagon_operations import HexagonGenerator

logger = logging.getLogger(__name__)

MAX_RESULTS = 60  # Text Search hard cap: 3 pages x 20
MAX_PAGES = 3


def log(db: Session, run_id: int, message: str, level: str = "info") -> None:
    db.add(RunLog(run_id=run_id, message=message, level=level))
    logger.info("run %s: %s", run_id, message)


def queue_run(db: Session, run: Run) -> None:
    """Create the base hex x keyword tasks for a new run."""
    codes = [a["area"] for a in run.areas]
    hex_area = regions.selection_hexes(codes, run.base_res)
    cells = [RunCell(run_id=run.id, hex_id=hx, res=run.base_res, keyword=kw, area=code)
             for kw in run.keywords for hx, code in hex_area.items()]
    db.add_all(cells)
    run.total_tasks = len(cells)
    run.raw_prefix = run_prefix(run.id, run.created_at.strftime("%Y-%m-%d_%H-%M-%S"))
    log(db, run.id, f"queued {len(hex_area)} cells x {len(run.keywords)} keywords at res {run.base_res}"
                    f" ({'mock' if run.mock else 'real API'})")


class Collector:
    def __init__(self, run_id: int):
        self.run_id = run_id
        self.settings = get_settings()
        self.hexes = HexagonGenerator()
        self.storage = Storage()
        self._place_pk: dict[str, int] = {}

    def run(self) -> None:
        try:
            with session_scope() as db:
                run = db.get(Run, self.run_id)
                if run.status not in ("queued", "running"):
                    return
                run.status = "running"
                self.mock = run.mock
                self.max_res = run.max_res
                self.prefix = run.raw_prefix
                self.locator = regions.AreaLocator([a["area"] for a in run.areas])
                self.city_of = {a["area"]: a["city"] for a in run.areas}
                self.client = MockPlaces() if run.mock else RealPlaces(self.settings.maps_api_key,
                                                                      self.settings.places_field_mask)
                self._place_pk = dict(db.execute(select(Place.place_id, Place.id).where(Place.run_id == run.id)).all())
                log(db, run.id, "collection started")
            self._loop()
        except Exception as e:  # noqa: BLE001  any failure ends the run with the reason shown in the UI
            logger.exception("run %s failed", self.run_id)
            with session_scope() as db:
                run = db.get(Run, self.run_id)
                run.status = "failed"
                run.error = f"{type(e).__name__}: {e}"
                run.finished_at = datetime.now(timezone.utc)
                log(db, self.run_id, f"failed: {run.error}", "error")
                log(db, self.run_id, traceback.format_exc(limit=3), "debug")

    def _loop(self) -> None:
        while True:
            with session_scope() as db:
                run = db.get(Run, self.run_id)
                if run.status == "cancelling":
                    run.status = "cancelled"
                    run.finished_at = datetime.now(timezone.utc)
                    log(db, run.id, "cancelled by user", "warn")
                    return
                # Depth-first: split children get higher ids but are taken before the next base cell
                cell = db.scalars(select(RunCell).where(RunCell.run_id == run.id, RunCell.status == "queued")
                                  .order_by(RunCell.res.desc(), RunCell.id).limit(1)).first()
                if cell is None:
                    self._finish(db, run)
                    return
                cell.status = "active"
            self._search_cell(cell.id)

    def _search_cell(self, cell_id: int) -> None:
        with session_scope() as db:
            cell = db.get(RunCell, cell_id)
            run = db.get(Run, self.run_id)
            bbox = self.hexes.get_hex_bbox(cell.hex_id)
            places: list[dict] = []
            token, page = None, 0
            while page < MAX_PAGES:
                page += 1
                res = self.client.search(cell.keyword, bbox, token)
                cost = places_call_usd()
                db.add(ApiCall(run_id=run.id, api="places.searchText", sku=PLACES_SKU, mock=self.mock,
                               status=res.status, latency_ms=res.latency_ms, cost_usd=cost, hex_id=cell.hex_id,
                               res=cell.res, keyword=cell.keyword, page=page, results=len(res.places)))
                run.api_calls += 1
                run.cost_usd += cost
                cell.calls += 1
                places.extend(res.places)
                token = res.next_page_token
                if not token:
                    break

            cell.results = len(places)
            run.raw_hits += len(places)
            new = self._store_places(db, run, cell, places)
            self._save_raw(cell, places)

            if len(places) >= MAX_RESULTS:
                if cell.res < self.max_res:
                    children = self.hexes.get_hexagon_children(cell.hex_id)
                    db.add_all(RunCell(run_id=run.id, hex_id=ch, res=cell.res + 1, keyword=cell.keyword,
                                       area=cell.area, parent=cell.hex_id) for ch in sorted(children))
                    cell.status = "split"
                    run.splits += 1
                    run.total_tasks += len(children)
                    log(db, run.id, f"{cell.hex_id} · {cell.keyword} · {len(places)} → split to res {cell.res + 1}")
                else:
                    cell.status = "saturated"
                    run.saturated += 1
                    log(db, run.id, f"{cell.hex_id} · {cell.keyword} · still {len(places)} at res {cell.res}"
                                    " (saturated, some places missed)", "warn")
            else:
                cell.status = "done"
                log(db, run.id, f"{cell.hex_id} · {cell.keyword} · {len(places)} places, {new} new")
            run.done_tasks += 1

    def _store_places(self, db: Session, run: Run, cell: RunCell, places: list[dict]) -> int:
        new = 0
        for p in places:
            pid = p.get("id")
            if not pid:
                continue
            pk = self._place_pk.get(pid)
            if pk:
                existing = db.get(Place, pk)
                existing.hits += 1
                if cell.keyword not in existing.keywords:
                    existing.keywords = existing.keywords + [cell.keyword]
                continue
            loc = p.get("location") or {}
            lat, lng = loc.get("latitude"), loc.get("longitude")
            row = Place(run_id=run.id, place_id=pid, hex_id=cell.hex_id, lat=lat, lng=lng,
                        area=self.locator.locate(lat, lng), keywords=[cell.keyword], hits=1, data=p)
            db.add(row)
            db.flush()
            self._place_pk[pid] = row.id
            new += 1
        run.unique_places += new
        return new

    def _save_raw(self, cell: RunCell, places: list[dict]) -> None:
        if not places:
            return
        df = pd.DataFrame(places)
        df["keyword"], df["hex_id"] = cell.keyword, cell.hex_id
        city = self.city_of.get(cell.area, "unknown")
        try:
            self.storage.put_csv(f"{self.prefix}/raw/{city}/{cell.hex_id}-{cell.keyword}.csv", df)
        except Exception as e:  # noqa: BLE001  raw CSVs are a backup; the DB is the source of truth
            logger.warning("raw upload failed for %s: %s", cell.hex_id, e)

    def _finish(self, db: Session, run: Run) -> None:
        rows = db.scalars(select(Place).where(Place.run_id == run.id)).all()
        if rows:
            df = pd.DataFrame([{**r.data, "keywords": "|".join(r.keywords), "hex_id": r.hex_id, "area": r.area,
                                "hits": r.hits} for r in rows])
            try:
                self.storage.put_csv(f"{self.prefix}/combined/data-extraction.csv", df)
            except Exception as e:  # noqa: BLE001
                log(db, run.id, f"combined CSV upload failed: {e}", "warn")
        run.status = "done"
        run.finished_at = datetime.now(timezone.utc)
        dupes = run.raw_hits - run.unique_places
        log(db, run.id, f"done · {run.unique_places:,} unique places from {run.raw_hits:,} hits "
                        f"({dupes:,} duplicates merged) · {run.api_calls:,} calls")


def recover_interrupted() -> None:
    """In thread mode a restart kills in-flight runs; mark them so the UI doesn't spin forever."""
    with session_scope() as db:
        db.execute(update(Run).where(Run.status.in_(("running", "cancelling", "queued")))
                   .values(status="failed", error="Interrupted by a server restart; start a new run"))
        db.execute(update(RunCell).where(RunCell.status == "active").values(status="queued"))
