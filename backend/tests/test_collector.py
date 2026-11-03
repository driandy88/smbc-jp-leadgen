import dataclasses
import threading
import time

import pandas as pd
import pytest
from sqlalchemy import func, select

from app.db import session_scope
from app.models import ApiCall, Place, Run
from app.services import collector, executor
from app.services.places_client import MockPlaces, RealPlaces
from app.settings import get_settings

# Kita + Chuo: two wards, so the area scheduler has something to balance
AREAS = [{"city": "osaka-shi", "area": "27127"}, {"city": "osaka-shi", "area": "27128"}]


@pytest.fixture
def queued_run(client, auth, monkeypatch):
    """Create a mock run without starting it, so the test drives the collector itself."""
    monkeypatch.setattr(executor, "start", lambda run_id: "job")

    def make(keywords=("居酒屋", "カフェ")):
        r = client.post("/api/runs", headers=auth, json={"keywords": list(keywords), "areas": AREAS,
                                                         "base_res": 8, "max_res": 9, "mock": True})
        return r.json()["id"]
    return make


def _workers(monkeypatch, n):
    s = dataclasses.replace(get_settings(), collect_workers=n)
    monkeypatch.setattr(collector, "get_settings", lambda: s)


def _run(run_id):
    with session_scope() as db:
        r = db.get(Run, run_id)
        places = set(db.scalars(select(Place.place_id).where(Place.run_id == run_id)).all())
        calls = db.scalar(select(func.count()).select_from(ApiCall).where(ApiCall.run_id == run_id))
        return {"status": r.status, "unique": r.unique_places, "raw": r.raw_hits, "api_calls": r.api_calls,
                "done": r.done_tasks, "total": r.total_tasks}, places, calls


def test_parallel_finds_the_same_places_as_sequential(queued_run, monkeypatch):
    _workers(monkeypatch, 1)
    one = queued_run()
    collector.Collector(one).run()
    _workers(monkeypatch, 8)
    par = queued_run()
    collector.Collector(par).run()

    a, places_a, calls_a = _run(one)
    b, places_b, calls_b = _run(par)
    assert a["status"] == b["status"] == "done"
    assert places_a == places_b and a["unique"] == b["unique"] and a["raw"] == b["raw"]
    assert a["api_calls"] == b["api_calls"] == calls_b and b["done"] == b["total"]


def test_workers_overlap_and_share_areas(queued_run, monkeypatch):
    _workers(monkeypatch, 4)
    lock, live, peak, order = threading.Lock(), [0], [0], []
    real_search = MockPlaces.search

    def slow(self, keyword, bbox, token):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.02)
        try:
            return real_search(self, keyword, bbox, token)
        finally:
            with lock:
                live[0] -= 1

    monkeypatch.setattr(MockPlaces, "search", slow)
    claim = collector.Collector._claim

    def spy(self, db, n, busy):
        out = claim(self, db, n, busy)
        order.extend(c["area"] for c in out)
        return out

    monkeypatch.setattr(collector.Collector, "_claim", spy)
    rid = queued_run(["居酒屋"])
    collector.Collector(rid).run()
    assert _run(rid)[0]["status"] == "done"
    assert peak[0] > 1  # searches really ran at the same time
    assert set(order[:4]) == {"27127", "27128"}  # the first batch is split across both wards


def test_cancel_mid_run_records_every_call(queued_run, monkeypatch):
    _workers(monkeypatch, 4)
    rid = queued_run()
    real_record = collector.Collector._record
    n = [0]

    def record(self, c, pages):
        real_record(self, c, pages)
        n[0] += 1
        if n[0] == 6:
            with session_scope() as db:
                db.get(Run, rid).status = "cancelling"

    monkeypatch.setattr(collector.Collector, "_record", record)
    collector.Collector(rid).run()
    r, _, calls = _run(rid)
    assert r["status"] == "cancelled"
    assert r["done"] < r["total"] and r["api_calls"] == calls  # in-flight searches finished and were logged


def test_rate_limiter_spaces_calls():
    lim = collector.RateLimiter(50)
    t0 = time.monotonic()
    threads = [threading.Thread(target=lim.wait) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert time.monotonic() - t0 >= 9 / 50 * 0.9


def test_real_client_retries_errors(monkeypatch):
    monkeypatch.setattr("app.services.places_client.time.sleep", lambda s: None)
    rp = RealPlaces.__new__(RealPlaces)
    replies = [pd.DataFrame(), pd.DataFrame(), {"places": [{"id": "a"}]}]
    rp.api = type("Api", (), {"text_search_api": lambda self, **kw: replies.pop(0)})()
    res = rp.search("居酒屋", (34.6, 135.4, 34.7, 135.5), None)
    assert res.status == "OK" and res.places == [{"id": "a"}]

    replies[:] = [pd.DataFrame()] * 3
    assert rp.search("居酒屋", (34.6, 135.4, 34.7, 135.5), None).status == "ERROR"


def test_estimate_is_json_safe_with_postgres_decimals():
    # Postgres AVG() returns Decimal; the estimate is stored in a JSON column on the run
    import json
    from decimal import Decimal

    from app.services import pricing

    class Db:
        def scalar(self, q):
            return Decimal("1234.5678")

    d = pricing.duration(Db(), 700)
    json.dumps(d)
    assert d["latency_s"] == 1.23 and d["minutes"] > 0
