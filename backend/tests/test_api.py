import time

from app.services import records, regions
from app.services.places_client import MockPlaces

AREAS = [{"city": "osaka-shi", "area": "27128"}]  # Chuo-ku


def test_login_rejects_wrong_password(client):
    assert client.post("/api/auth/login", json={"email": "daniel.riandy@artefact.com", "password": "nope"}).status_code == 401


def test_api_requires_auth(client):
    assert client.get("/api/runs").status_code == 401


def test_osaka_wards_from_n03():
    city = next(c for c in regions.cities() if c["key"] == "osaka-shi")
    assert city["areas"] == 24
    assert 220 < city["km2"] < 232  # official: 225 km²


def test_mock_saturates_in_dense_cells_only():
    import h3

    m = MockPlaces(latency_s=0)

    def bbox(lat, lng, res):
        v = h3.h3_to_geo_boundary(h3.geo_to_h3(lat, lng, res))
        la, lo = [p[0] for p in v], [p[1] for p in v]
        return min(la), min(lo), max(la), max(lo)

    umeda = m.search("居酒屋", bbox(34.7025, 135.4959, 8), None)
    assert len(umeda.places) == 20 and umeda.next_page_token
    assert m.search("居酒屋", bbox(34.7025, 135.4959, 8), None).places[0]["id"] == umeda.places[0]["id"]


def test_estimate(client, auth):
    r = client.post("/api/scout/estimate", headers=auth,
                    json={"keywords": ["居酒屋", "カフェ"], "areas": AREAS, "base_res": 8, "max_res": 10}).json()
    assert r["tasks"] == r["cells"] * 2 and r["expected_calls"] >= r["min_calls"]


def test_real_run_needs_key(client, auth):
    r = client.post("/api/runs", headers=auth, json={"keywords": ["居酒屋"], "areas": AREAS, "mock": False})
    assert r.status_code == 422


def test_mock_run_end_to_end(client, auth):
    run = client.post("/api/runs", headers=auth,
                      json={"keywords": ["居酒屋", "焼き鳥"], "areas": AREAS, "base_res": 8, "max_res": 9, "mock": True}).json()
    for _ in range(300):
        s = client.get(f"/api/runs/{run['id']}", headers=auth).json()
        if s["status"] not in ("queued", "running"):
            break
        time.sleep(0.5)
    assert s["status"] == "done", s.get("error")
    assert s["unique_places"] > 0 and s["raw_hits"] >= s["unique_places"]
    assert s["done_tasks"] == s["total_tasks"]
    # Same-family keywords overlap, so some places are merged
    assert s["dupes"] > 0

    f = client.post(f"/api/runs/{run['id']}/filter", headers=auth, json={"pay": ["cash"]}).json()
    assert 0 < f["count"] < f["total"]
    assert f["funnel"][-1]["n"] == f["count"]
    assert {"phone", "web"} <= f["preview"][0].keys()
    revs = [r["reviews"] for r in f["preview"] if r["reviews"] is not None]
    assert revs == sorted(revs, reverse=True)  # default: most reviewed first
    by = lambda sort, **q: client.post(f"/api/runs/{run['id']}/filter", headers=auth, params={"sort": sort, **q}, json={}).json()["preview"]  # noqa: E731
    rated = [r["rating"] for r in by("rating", desc=False) if r["rating"] is not None]
    assert rated == sorted(rated)
    names = [r["name"] for r in by("name")]
    assert names == sorted(names)
    contact = [(r["phone"] is not None) + (r["web"] is not None) for r in by("contact")]
    assert contact == sorted(contact, reverse=True)

    v = client.post("/api/versions", headers=auth, json={"run_id": run["id"], "name": "test_v1", "filters": {}}).json()
    assert v["rows"] > 0
    a = client.post(f"/api/versions/{v['id']}/analyze", headers=auth).json()
    assert len(a["summary"]["kpis"]) == 4 and a["summary"]["where"] and a["profile"]["rows"] == v["rows"]
    prof = a["profile"]
    assert sum(h["places"] for h in prof["hexes"]["rows"]) <= prof["rows"] and prof["hexes"]["rows"][0]["types"]
    assert {k["keyword"] for k in prof["keywords"]} == {"居酒屋", "焼き鳥"}
    assert prof["kw_en"] == {"居酒屋": "Izakaya", "焼き鳥": "Yakitori"}
    assert prof["hexes"]["rows"][0]["area"] == "Chuo" and f["preview"][0]["area"] == "Chuo"
    assert prof["fnb"]["core"]["n"] + prof["fnb"]["related"]["n"] + prof["fnb"]["no"]["n"] == prof["rows"]

    # Merchant mix: areas, types and contact splits each add up to the full list
    assert sum(a["places"] for a in prof["areas"]) == prof["rows"]
    assert all(sum(a["fnb"].values()) == a["places"] for a in prof["areas"])
    assert sum(t["n"] for t in prof["type_mix"]) == prof["rows"]
    c = prof["contact"]
    assert sum(x["n"] for x in c["split"].values()) == prof["rows"]
    assert c["either"] + c["neither"] == prof["rows"] and sum(k["n"] for k in c["web_kinds"]) == c["web"]
    hx = prof["hexes"]
    assert len(hx["rows"]) == hx["cells"] and sum(d["merchants"] for d in hx["dist"]) == hx["cells"]
    assert sum(r["fnb"] for r in hx["rows"]) == prof["fnb"]["core"]["n"]
    assert 0 < hx["fnb_half_cells"] <= hx["fnb_80_cells"] <= hx["cells"]
    assert {i["k"] for i in prof["insights"]} >= {"Mix", "Contact", "Hotspot", "Segments"}

    # Business view: F&B segments add up to the F&B list, hotspots are named and ranked by density
    fnb_n = prof["fnb"]["core"]["n"] + prof["fnb"]["related"]["n"]
    assert sum(s_["n"] for s_ in prof["fnb_segments"]) == fnb_n
    hs = prof["hotspots"]
    assert hs and all(h["name"] and h["density_km2"] > 0 and "leads" not in h for h in hs)
    assert all(h["n"] <= fnb_n for h in hs)  # hotspots count F&B merchants only
    assert [h["density_km2"] for h in hs] == sorted((h["density_km2"] for h in hs), reverse=True)

    # Keyword selection: duplicates split into same-term repeats and cross-term overlap, cover curve reaches 100%
    ks = prof["keyword_set"]
    assert ks["raw_hits"] == s["raw_hits"] and ks["dupes"] == s["dupes"]
    assert ks["repeats_same_term"] + ks["found_by_several"] == ks["dupes"]
    assert ks["curve"][-1]["cum_pct"] == 100 and sum(c["gain"] for c in ks["curve"]) == prof["rows"]
    assert sum(k["calls"] for k in prof["keywords"]) == s["api_calls"]

    # Map points: one per merchant, filtered like the step they come from
    pts = client.get(f"/api/versions/{v['id']}/points", headers=auth).json()
    assert len(pts["rows"]) == v["rows"] and all(len(r) == len(pts["cols"]) for r in pts["rows"])
    assert "lead" not in pts["cols"] and {"segment", "district", "phone", "web"} <= set(pts["cols"])
    cash = client.post(f"/api/runs/{run['id']}/points", headers=auth, json={"pay": ["cash"]}).json()
    assert len(cash["rows"]) == f["count"]

    # Every Places call is in the ledger
    assert client.get("/api/billing/summary", headers=auth).status_code == 403
    tok = client.post("/api/billing/unlock", headers=auth, json={"passcode": "test12345"}).json()["token"]
    calls = client.get(f"/api/billing/calls?run_id={run['id']}&api=places.searchText",
                       headers=auth | {"X-Billing-Token": tok}).json()
    assert calls["total"] == s["api_calls"]


def test_open_at_handles_overnight():
    # Friday 18:00 → Saturday 02:00
    iv = [(5 * 1440 + 18 * 60, 6 * 1440 + 2 * 60)]
    assert records.open_at(iv, 6 * 1440 + 60)
    assert not records.open_at(iv, 6 * 1440 + 3 * 60)


def test_fnb_class_on_real_shapes():
    izakaya = {"primaryType": "japanese_izakaya_restaurant", "types": ["japanese_izakaya_restaurant", "restaurant", "food"]}
    kakuuchi = {"primaryType": "liquor_store", "types": ["liquor_store", "store", "food"], "servesBeer": True}
    karaoke = {"primaryType": "karaoke", "types": ["karaoke", "night_club"], "servesBeer": True}
    hotel = {"primaryType": "hotel", "types": ["hotel", "lodging"]}
    assert records.fnb_class(izakaya) == ("core", "primaryType")
    assert records.fnb_class({"primaryType": "bar", "types": ["bar"]})[0] == "core"
    assert records.fnb_class(kakuuchi) == ("related", "types")
    assert records.fnb_class(karaoke) == ("related", "dining attributes")
    assert records.fnb_class(hotel) == ("no", "none")


def test_cancel_before_job_starts_does_not_hang(client, auth, monkeypatch):
    # Job mode: the run sits queued until the job boots, and the user may cancel in that gap
    from app.services import collector, executor
    monkeypatch.setattr(executor, "start", lambda run_id: "job")
    run = client.post("/api/runs", headers=auth, json={"keywords": ["居酒屋"], "areas": AREAS, "mock": True}).json()
    assert client.post(f"/api/runs/{run['id']}/cancel", headers=auth).json()["status"] == "cancelled"
    collector.Collector(run["id"]).run()  # the late job must leave it alone
    assert client.get(f"/api/runs/{run['id']}", headers=auth).json()["status"] == "cancelled"

    # A run stuck in cancelling (job died) is closed by the job if it boots late, or by a second cancel
    run = client.post("/api/runs", headers=auth, json={"keywords": ["居酒屋"], "areas": AREAS, "mock": True}).json()
    from app.db import session_scope
    from app.models import Run
    with session_scope() as db:
        db.get(Run, run["id"]).status = "cancelling"
    collector.Collector(run["id"]).run()
    assert client.get(f"/api/runs/{run['id']}", headers=auth).json()["status"] == "cancelled"
    run = client.post("/api/runs", headers=auth, json={"keywords": ["居酒屋"], "areas": AREAS, "mock": True}).json()
    with session_scope() as db:
        db.get(Run, run["id"]).status = "cancelling"
    assert client.post(f"/api/runs/{run['id']}/cancel", headers=auth).json()["status"] == "cancelled"


def test_web_kind():
    from app.services.analysis import web_kind
    assert web_kind("https://www.instagram.com/izakaya_x/") == "social"
    assert web_kind("https://lin.ee/abc") == "social"
    assert web_kind("https://tabelog.com/osaka/A2701/") == "portal"
    assert web_kind("https://beauty.hotpepper.jp/slnH0001/") == "portal"
    assert web_kind("https://izakaya-x.jp/") == "own"
    assert web_kind(None) is None


def test_type_labels_are_english():
    assert records.type_en("ramen_restaurant") == "Ramen restaurant"
    assert records.type_en("japanese_izakaya_restaurant") == "Izakaya"
    assert records.type_en(None) == "Other"


def test_segments_and_districts():
    from app.services import districts
    assert districts.segment("barbecue_restaurant", "core") == "Yakiniku & grill"
    assert districts.segment("steak_house", "core") == "Yakiniku & grill"
    assert districts.segment("japanese_izakaya_restaurant", "core") == "Izakaya & bars"
    assert districts.segment("coffee_shop", "core") == "Cafe, bakery & sweets"
    assert districts.segment("hotel", "no") == "Not F&B"
    en, jp = districts.assign([34.7025, 34.6687, 34.80], [135.4959, 135.5013, 135.60], ["Kita", "Chuo", "Kita"])
    assert en == ["Umeda", "Dotonbori", "Kita · other"] and jp[0] == "梅田"


def test_summary_explanation(client, auth):
    # The Summary step's AI read: rule-based on mock runs, same shape as the model's output
    runs = client.get("/api/runs", headers=auth).json()
    done = next(r for r in runs if r["status"] == "done")
    e = client.post(f"/api/runs/{done['id']}/explain", headers=auth, json={}).json()
    assert e["headline"] and e["summary"] and 1 <= len(e["points"]) <= 5
    assert all(p["topic"] and p["text"] for p in e["points"])
    assert client.post(f"/api/runs/{done['id']}/explain", headers=auth, json={}).json() == e  # cached


def test_gemini_call_shape(monkeypatch):
    # Gemini on Vertex: schema converted to Vertex's format, thinking parts skipped, tokens billed incl. thinking
    import json as _json

    from app.services import summary

    sent = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [
                {"text": "thinking...", "thought": True}, {"text": _json.dumps({"headline": "h", "summary": "s", "points": []})}]}}],
                "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 100, "thoughtsTokenCount": 400}}

    class Session:
        def __init__(self, creds):
            pass

        def post(self, url, json, timeout):
            sent.update(url=url, body=json)
            return Resp()

    import google.auth
    import google.auth.transport.requests as gtr
    monkeypatch.setattr(google.auth, "default", lambda scopes: (None, "p"))
    monkeypatch.setattr(gtr, "AuthorizedSession", Session)
    out, call = summary._gemini(summary.EXPLAIN_SYSTEM, summary.EXPLAIN_SCHEMA, {"rows": 1}, 1500, "low")
    assert out["headline"] == "h" and call["tokens_out"] == 500 and call["cost_usd"] > 0
    schema = sent["body"]["generationConfig"]["responseSchema"]
    assert schema["type"] == "OBJECT" and "additionalProperties" not in schema
    assert schema["properties"]["points"]["items"]["properties"]["topic"]["type"] == "STRING"
    assert sent["url"].endswith("/publishers/google/models/gemini-3.5-flash:generateContent")


def test_combine_versions_dedupes_and_keeps_sources(client, auth):
    def run(keywords, areas):
        r = client.post("/api/runs", headers=auth, json={"keywords": keywords, "areas": areas,
                                                         "base_res": 8, "max_res": 9, "mock": True}).json()
        for _ in range(300):
            if client.get(f"/api/runs/{r['id']}", headers=auth).json()["status"] not in ("queued", "running"):
                return r["id"]
            time.sleep(0.5)

    # Two runs over overlapping wards and keywords, so some places are in both
    a = run(["居酒屋"], [{"city": "osaka-shi", "area": "27128"}])
    b = run(["居酒屋", "カフェ"], [{"city": "osaka-shi", "area": "27128"}, {"city": "osaka-shi", "area": "27127"}])
    va = client.post("/api/versions", headers=auth, json={"run_id": a, "name": "combo_a", "filters": {}}).json()
    vb = client.post("/api/versions", headers=auth, json={"run_id": b, "name": "combo_b", "filters": {}}).json()

    assert client.post("/api/versions/combine", headers=auth, json={"version_ids": [va["id"]], "name": "x"}).status_code == 422
    pre = client.post("/api/versions/combine", headers=auth, json={"version_ids": [va["id"], vb["id"]], "dry_run": True}).json()
    assert pre["rows_in"] == va["rows"] + vb["rows"] and pre["duplicates"] > 0
    c = client.post("/api/versions/combine", headers=auth,
                    json={"version_ids": [va["id"], vb["id"]], "name": "combo_ab", "notes": "Chuo + Kita"}).json()
    assert c["rows"] == pre["rows"] == pre["rows_in"] - pre["duplicates"]
    assert [s["name"] for s in c["sources"]] == ["combo_a", "combo_b"] and c["areas"] == 2 and c["keywords"] == 2
    assert client.post("/api/versions/combine", headers=auth,
                       json={"version_ids": [va["id"], vb["id"]], "name": "combo_ab"}).status_code == 409

    # Sources untouched, the export has each place once, and the combined version analyses like any other
    listed = {v["name"]: v for v in client.get("/api/versions", headers=auth).json()}
    assert listed["combo_a"]["rows"] == va["rows"] and listed["combo_b"]["rows"] == vb["rows"] and listed["combo_a"]["sources"] is None
    csv = client.get(f"/api/versions/{c['id']}/export.csv", headers=auth).content.decode("utf-8-sig").splitlines()
    ids = [line.split(",")[0] for line in csv[1:]]
    assert len(ids) == len(set(ids)) == c["rows"]
    p = client.post(f"/api/versions/{c['id']}/analyze", headers=auth).json()["profile"]
    assert p["rows"] == c["rows"] and len(p["run"]["areas"]) == 2
    assert len(client.get(f"/api/versions/{c['id']}/points", headers=auth).json()["rows"]) == c["rows"]

    # A combined version can itself be combined
    cc = client.post("/api/versions/combine", headers=auth, json={"version_ids": [c["id"], va["id"]], "name": "combo_abc"}).json()
    assert cc["rows"] == c["rows"] and cc["duplicates"] == va["rows"]
