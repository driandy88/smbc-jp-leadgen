"""Text Search clients. `RealPlaces` wraps modules.google_maps.GoogleMapsAPI; `MockPlaces` fakes it.

Both return the raw Places API (New) response shape, so the collector cannot tell them apart.
"""

import hashlib
import math
import random
import time
from dataclasses import dataclass
from functools import lru_cache

import h3
import pandas as pd

from modules.google_maps.api import GoogleMapsAPI


@dataclass
class SearchResult:
    places: list[dict]
    next_page_token: str | None
    status: str  # OK | ERROR:<status>
    latency_ms: int


class RealPlaces:
    def __init__(self, api_key: str, field_mask: str, language_code: str = "ja", region_code: str = "JP"):
        if not api_key:
            raise RuntimeError("GOOGLE_MAPS_API_KEY is not set; switch the run to Mock or add the key")
        self.api = GoogleMapsAPI(field_mask=field_mask, api_key=api_key,
                                 language_code=language_code, region_code=region_code)

    RETRIES = 3

    def search(self, keyword: str, bbox: tuple[float, float, float, float], page_token: str | None) -> SearchResult:
        min_lat, min_lng, max_lat, max_lng = bbox
        t0 = time.perf_counter()
        for attempt in range(self.RETRIES):
            # Raises PermissionError on a bad key / disabled API, which fails the run
            res = self.api.text_search_api(text_query=keyword, min_lat=min_lat, min_lng=min_lng,
                                           max_lat=max_lat, max_lng=max_lng, nextPageToken=page_token)
            # The module returns an empty DataFrame on transport/API errors, including rate limiting
            # (429), so back off and retry instead of recording the cell as empty
            if not isinstance(res, pd.DataFrame):
                ms = int((time.perf_counter() - t0) * 1000)
                return SearchResult(res.get("places", []) or [], res.get("nextPageToken"), "OK", ms)
            if attempt < self.RETRIES - 1:
                time.sleep((2 ** attempt) * (1 + random.random()))
        return SearchResult([], None, "ERROR", int((time.perf_counter() - t0) * 1000))


# ---------------------------------------------------------------------------------------------
# Mock

# Busy districts; density falls off with distance (lat, lng, weight, sigma km)
HOTSPOTS = [
    (34.7025, 135.4959, 1.0, 0.9),   # Umeda
    (34.6687, 135.5013, 1.0, 0.8),   # Namba / Dotonbori
    (34.6745, 135.5005, 0.8, 0.6),   # Shinsaibashi
    (34.7047, 135.5118, 0.7, 0.5),   # Tenma
    (34.6466, 135.5133, 0.6, 0.6),   # Tennoji / Abeno
    (34.6937, 135.4844, 0.4, 0.5),   # Fukushima
    (34.6530, 135.5060, 0.5, 0.4),   # Shinsekai
    (35.0037, 135.7681, 0.9, 0.7),   # Kawaramachi
    (35.0037, 135.7756, 0.6, 0.4),   # Gion
    (34.9858, 135.7588, 0.6, 0.6),   # Kyoto station
    (34.5733, 135.4830, 0.4, 0.6),   # Sakai-Higashi
]

# primaryType mix per keyword family (keys match keywords.GROUPS)
FAMILY_TYPES = {
    "drink": ["japanese_izakaya_restaurant"] * 3 + ["bar", "japanese_restaurant"],
    "bar": ["bar", "bar", "pub", "wine_bar"],
    "noodle": ["ramen_restaurant", "ramen_restaurant", "japanese_restaurant"],
    "washoku": ["japanese_restaurant", "sushi_restaurant", "japanese_restaurant"],
    "grill": ["yakiniku_restaurant", "barbecue_restaurant", "japanese_restaurant"],
    "cafe": ["cafe", "coffee_shop", "bakery"],
    "world": ["chinese_restaurant", "italian_restaurant", "french_restaurant", "korean_restaurant", "indian_restaurant"],
    "quick": ["fast_food_restaurant", "japanese_curry_restaurant", "restaurant"],
}
TYPE_LABEL = {
    "japanese_izakaya_restaurant": "居酒屋", "bar": "バー", "pub": "パブ", "wine_bar": "ワインバー",
    "ramen_restaurant": "ラーメン屋", "cafe": "カフェ", "coffee_shop": "コーヒーショップ", "sushi_restaurant": "寿司屋",
    "yakiniku_restaurant": "焼肉店", "barbecue_restaurant": "バーベキュー", "japanese_restaurant": "和食店",
    "fast_food_restaurant": "ファストフード", "chinese_restaurant": "中華料理店", "bakery": "ベーカリー",
    "italian_restaurant": "イタリア料理店", "french_restaurant": "フランス料理店", "korean_restaurant": "韓国料理店",
    "indian_restaurant": "インド料理店", "japanese_curry_restaurant": "カレー屋", "restaurant": "レストラン",
}
NAMES = ["ほたる", "まる吉", "千鳥", "夕凪", "銀杏", "灯", "三日月", "楓", "松風", "鶴亀", "八兵衛", "小町", "はなび",
         "福来", "こはる", "大黒屋", "ひさご", "山茶花", "新月", "ことぶき", "寅吉", "まめだ", "ろくろ", "のれん",
         "十六夜", "藤", "いろは", "かもめ", "よし川", "きらく", "一福", "さくら", "とら", "えびす", "天満屋"]
CHAINS = ["鳥貴族", "串カツ田中", "スシロー", "コメダ珈琲店", "スターバックス", "一蘭", "餃子の王将", "すき家"]

# Real pulls include some non-F&B hits (角打ち liquor stores, karaoke, konbini, hotels)
NON_FNB = [
    ("liquor_store", ["liquor_store", "store", "food", "point_of_interest", "establishment"], "酒屋", True),
    ("karaoke", ["karaoke", "night_club", "point_of_interest", "establishment"], "カラオケ", True),
    ("convenience_store", ["convenience_store", "food_store", "store", "point_of_interest", "establishment"], "コンビニ", False),
    ("hotel", ["hotel", "lodging", "point_of_interest", "establishment"], "ホテル", False),
    ("event_venue", ["event_venue", "banquet_hall", "point_of_interest", "establishment"], "宴会場", True),
]

MOCK_RES = 10       # the fake universe is generated per res-10 cell
PEAK_PER_CELL = 5.0  # places per res-10 cell (~0.015 km²) at the heart of a hotspot, per keyword family


def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12], 16))


def _density(lat: float, lng: float) -> float:
    d = 0.04
    for hlat, hlng, w, sigma in HOTSPOTS:
        dy = (lat - hlat) * 111.0
        dx = (lng - hlng) * 111.0 * math.cos(math.radians(lat))
        d += w * math.exp(-(dx * dx + dy * dy) / (2 * sigma * sigma))
    return min(d, 1.2)


def _family(keyword: str) -> str:
    # Keywords in one family share places, so overlapping terms produce duplicates like the real API
    from app.services.keywords import GROUPS

    for key, _, terms in GROUPS:
        if any(t[0] == keyword for t in terms):
            return key
    return "custom:" + keyword


@lru_cache(maxsize=200_000)
def _cell_places(cell: str, family: str) -> tuple:
    lat, lng = h3.h3_to_geo(cell)
    r = _rng(cell, family)
    lam = PEAK_PER_CELL * _density(lat, lng)
    n, acc, limit = 0, r.random(), math.exp(-lam)  # Poisson(lam), Knuth
    while acc > limit:
        n += 1
        acc *= r.random()
    boundary = h3.h3_to_geo_boundary(cell)
    lats = [p[0] for p in boundary]
    lngs = [p[1] for p in boundary]
    return tuple(_make_place(cell, family, i, r.uniform(min(lats), max(lats)), r.uniform(min(lngs), max(lngs)))
                 for i in range(n))


def _make_place(cell: str, family: str, i: int, lat: float, lng: float) -> dict:
    r = _rng(cell, family, i)
    pid = "mock_" + hashlib.sha1(f"{cell}{family}{i}".encode()).hexdigest()[:24]
    ptype = r.choice(FAMILY_TYPES.get(family) or ["restaurant"])
    chain = r.random() < 0.08
    name = r.choice(CHAINS) + " " + r.choice(["梅田店", "難波店", "天満店", "心斎橋店", "京都駅前店"]) if chain \
        else f"{r.choice(['', '炭火', '大衆', '立呑み ', '酒処 ', '麺屋 ', '喫茶 '])}{r.choice(NAMES)}{r.choice(NAMES)}"
    status = r.choices(["OPERATIONAL", "CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"], [0.93, 0.02, 0.05])[0]
    unrated = r.random() < 0.03
    rating = None if unrated else round(max(2.3, min(4.8, r.gauss(3.6, 0.32))), 1)
    reviews = None if unrated else max(1, int(math.exp(r.gauss(3.4, 1.3))))
    p: dict = {
        "id": pid,
        "name": f"places/{pid}",
        "displayName": {"text": name, "languageCode": "ja"},
        "formattedAddress": f"日本、〒530-0001 大阪府大阪市 {r.randint(1, 9)}-{r.randint(1, 30)}-{r.randint(1, 20)}",
        "location": {"latitude": lat, "longitude": lng},
        "types": [ptype, "restaurant", "food", "point_of_interest", "establishment"],
        "primaryType": ptype,
        "primaryTypeDisplayName": {"text": TYPE_LABEL.get(ptype, ptype), "languageCode": "ja"},
        "businessStatus": status,
        "googleMapsUri": f"https://maps.google.com/?cid={int(pid[5:17], 16)}",
        "utcOffsetMinutes": 540,
    }
    if rating is not None:
        p["rating"] = rating
        p["userRatingCount"] = reviews
    if r.random() < 0.9:
        p["nationalPhoneNumber"] = f"06-{r.randint(6000, 6999)}-{r.randint(1000, 9999)}"
    if r.random() < 0.4 or chain:
        p["websiteUri"] = f"https://example.jp/{pid[5:13]}"
    if r.random() < 0.92:
        p["photos"] = [{"name": f"places/{pid}/photos/{k}"} for k in range(r.randint(1, 10))]
    if r.random() < 0.62:
        start = r.choice([1000, 2000, 3000, 4000, 5000, 6000])
        p["priceRange"] = {"startPrice": {"currencyCode": "JPY", "units": str(start)},
                           "endPrice": {"currencyCode": "JPY", "units": str(start + r.choice([1000, 2000]))}}
    if r.random() < 0.5:
        p["priceLevel"] = r.choice(["PRICE_LEVEL_INEXPENSIVE", "PRICE_LEVEL_MODERATE", "PRICE_LEVEL_EXPENSIVE"])
    if r.random() < 0.05:
        ptype, types, label, dining = r.choice(NON_FNB)
        p.update({"types": types, "primaryType": ptype, "primaryTypeDisplayName": {"text": label, "languageCode": "ja"}})
        p["_dining"] = dining
    if r.random() < 0.7:
        cash_only = r.random() < (0.35 if not chain else 0.02)
        p["paymentOptions"] = {"acceptsCashOnly": cash_only, "acceptsCreditCards": not cash_only and r.random() < 0.85,
                               "acceptsNfc": not cash_only and r.random() < 0.45, "acceptsDebitCards": False}
    if r.random() < 0.88:
        p["regularOpeningHours"] = _hours(r, ptype)
    no_dining = not p.pop("_dining", True)
    for k, prob in [] if no_dining else [("dineIn", 0.95), ("takeout", 0.3), ("delivery", 0.1), ("reservable", 0.45),
                    ("servesBeer", 0.8 if "cafe" not in ptype else 0.1), ("servesLunch", 0.5), ("servesDinner", 0.8)]:
        if r.random() < 0.85:
            p[k] = r.random() < prob
    return p


def _hours(r: random.Random, ptype: str) -> dict:
    if ptype in ("cafe", "coffee_shop", "bakery"):
        o, c = r.choice([(7, 18), (8, 19), (10, 20)])
    elif ptype in ("bar", "pub", "wine_bar", "japanese_izakaya_restaurant"):
        o, c = r.choice([(17, 24), (16, 23), (18, 26)])
    else:
        o, c = r.choice([(11, 22), (11, 23), (11, 21)])
    closed = {r.choice([0, 1, 2, 3])} if r.random() < 0.6 else set()
    periods = []
    for d in range(7):
        if d in closed:
            continue
        cd, ch = (d + c // 24) % 7, c % 24
        periods.append({"open": {"day": d, "hour": o, "minute": 0}, "close": {"day": cd, "hour": ch, "minute": 0}})
    return {"openNow": False, "periods": periods}


class MockPlaces:
    """Deterministic fake universe: the same bbox + keyword always returns the same places."""

    def __init__(self, latency_s: float = 0.03):
        self.latency_s = latency_s

    def search(self, keyword: str, bbox: tuple[float, float, float, float], page_token: str | None) -> SearchResult:
        t0 = time.perf_counter()
        min_lat, min_lng, max_lat, max_lng = bbox
        family = _family(keyword)
        poly = {"type": "Polygon", "coordinates": [[[min_lng, min_lat], [max_lng, min_lat], [max_lng, max_lat],
                                                    [min_lng, max_lat], [min_lng, min_lat]]]}
        cells = h3.polyfill(poly, MOCK_RES, geo_json_conformant=True)
        hits = []
        for cell in cells:
            for p in _cell_places(cell, family):
                loc = p["location"]
                if min_lat <= loc["latitude"] <= max_lat and min_lng <= loc["longitude"] <= max_lng:
                    # Roughly 75% of a family's places match any given term in it
                    if _rng(p["id"], keyword).random() < 0.75 or family.startswith("custom:"):
                        hits.append(p)
        # Google ranks by relevance; we fake it with a stable hash, capped at 60 like the real API
        hits.sort(key=lambda p: hashlib.md5((p["id"] + keyword).encode()).hexdigest())
        hits = hits[:60]
        offset = int(page_token.split(":")[1]) if page_token else 0
        page = [dict(p) for p in hits[offset:offset + 20]]
        nxt = f"mock:{offset + 20}" if offset + 20 < len(hits) else None
        if self.latency_s:
            time.sleep(self.latency_s * (0.5 + random.random()))
        return SearchResult(page, nxt, "OK", int((time.perf_counter() - t0) * 1000))
