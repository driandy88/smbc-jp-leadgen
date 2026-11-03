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

    v = client.post("/api/versions", headers=auth, json={"run_id": run["id"], "name": "test_v1", "filters": {}}).json()
    assert v["rows"] > 0
    a = client.post(f"/api/versions/{v['id']}/analyze", headers=auth).json()
    assert len(a["summary"]["kpis"]) == 4 and a["summary"]["where"] and a["profile"]["rows"] == v["rows"]
    prof = a["profile"]
    assert sum(h["places"] for h in prof["hexes"]["rows"]) <= prof["rows"] and prof["hexes"]["rows"][0]["types"]
    assert {k["keyword"] for k in prof["keywords"]} == {"居酒屋", "焼き鳥"}
    assert prof["fnb"]["core"]["n"] + prof["fnb"]["related"]["n"] + prof["fnb"]["no"]["n"] == prof["rows"]

    # Map points: one per merchant, filtered like the step they come from
    pts = client.get(f"/api/versions/{v['id']}/points", headers=auth).json()
    assert len(pts["rows"]) == v["rows"] and all(len(r) == len(pts["cols"]) for r in pts["rows"])
    assert sum(r[pts["cols"].index("lead")] for r in pts["rows"]) == prof["segments"]["priority"]["n"]
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
