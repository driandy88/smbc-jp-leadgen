"""Flatten raw Places JSON into one row per place, and apply the Filter-step rules to it."""

from functools import lru_cache

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.db import session_scope
from app.models import Place, Run
from app.services import districts, regions

PRICE_BANDS = ["〜¥1,000", "¥1,000–2,000", "¥2,000–3,000", "¥3,000–5,000", "¥5,000+", "No info"]
PRICE_LEVEL_BAND = {"PRICE_LEVEL_INEXPENSIVE": 0, "PRICE_LEVEL_MODERATE": 1, "PRICE_LEVEL_EXPENSIVE": 3,
                    "PRICE_LEVEL_VERY_EXPENSIVE": 4}
PAY = {"cash": "Cash only", "none": "No payment info", "card": "Card", "nfc": "Card + NFC / IC"}
STATUS = {"OPERATIONAL": "Operational", "CLOSED_TEMPORARILY": "Temporarily closed",
          "CLOSED_PERMANENTLY": "Permanently closed"}
SERVICES = {"dineIn": "Dine-in", "takeout": "Takeout", "delivery": "Delivery", "reservable": "Reservable",
            "servesBeer": "Serves beer", "servesLunch": "Lunch", "servesDinner": "Dinner"}
QUALITY = {"phone": "Has phone number", "web": "Has website", "photos": "5+ photos", "nochain": "Exclude chains"}
REVIEW_STEPS = [0, 5, 10, 20, 50, 100, 200, 500, 1000]

# F&B detection from Google's own fields. Google has no "is F&B" flag, but three signals together
# are reliable: the primaryType, the full `types` list, and dining attributes (dineIn, serves*),
# which Google only fills in for venues that serve food or drink.
FNB_PRIMARY = {
    "restaurant", "bar", "cafe", "coffee_shop", "bakery", "pub", "brewpub", "bistro", "steak_house", "deli",
    "food_court", "meal_takeaway", "meal_delivery", "dessert_shop", "dessert_restaurant", "tea_house",
    "ice_cream_shop", "juice_shop", "sandwich_shop", "bagel_shop", "donut_shop", "confectionery", "wine_bar",
    "cocktail_bar", "snack_bar", "beer_garden", "diner", "cafeteria", "chocolate_shop", "acai_shop",
    "bar_and_grill", "noodle_shop", "candy_store", "pastry_shop",
}
FNB_TYPES = {"food", "restaurant", "bar", "cafe", "meal_takeaway", "meal_delivery"}
DINING_FIELDS = ("dineIn", "servesBeer", "servesWine", "servesCoffee", "servesBreakfast", "servesLunch",
                 "servesDinner", "servesDessert", "servesBrunch", "servesCocktails", "servesVegetarianFood")
FNB_LABEL = {"core": "F&B", "related": "F&B-related", "no": "Not F&B"}


def fnb_class(p: dict) -> tuple[str, str]:
    """('core' | 'related' | 'no', the signal that decided it)."""
    primary = p.get("primaryType") or ""
    if primary in FNB_PRIMARY or primary.endswith(("_restaurant", "_bar", "_cafe")):
        return "core", "primaryType"
    if FNB_TYPES & set(p.get("types") or []):
        return "related", "types"
    if any(k in p for k in DINING_FIELDS):
        return "related", "dining attributes"
    return "no", "none"
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]  # Google's day 0 is Sunday


def _price_band(p: dict) -> int:
    start = (p.get("priceRange") or {}).get("startPrice", {}).get("units")
    if start is not None:
        v = int(start)
        return 0 if v < 1000 else 1 if v < 2000 else 2 if v < 3000 else 3 if v < 5000 else 4
    return PRICE_LEVEL_BAND.get(p.get("priceLevel"), 5)


def _pay(p: dict) -> str:
    po = p.get("paymentOptions")
    if not po:
        return "none"
    if po.get("acceptsNfc"):
        return "nfc"
    if po.get("acceptsCreditCards") or po.get("acceptsDebitCards"):
        return "card"
    if po.get("acceptsCashOnly") or po.get("acceptsCreditCards") is False:
        return "cash"
    return "none"


def _intervals(p: dict) -> list[tuple[int, int]]:
    """Weekly open intervals in minutes from Sunday 00:00; overnight periods wrap past Saturday."""
    out = []
    for per in (p.get("regularOpeningHours") or {}).get("periods", []):
        o, c = per.get("open"), per.get("close")
        if not o:
            continue
        start = o["day"] * 1440 + o.get("hour", 0) * 60 + o.get("minute", 0)
        if not c:  # open 24h
            out.append((0, 7 * 1440))
            continue
        end = c["day"] * 1440 + c.get("hour", 0) * 60 + c.get("minute", 0)
        if end <= start:
            end += 7 * 1440
        out.append((start, end))
    return out


def open_at(intervals: list[tuple[int, int]], minute_of_week: int) -> bool:
    for s, e in intervals:
        if s <= minute_of_week < e or s <= minute_of_week + 7 * 1440 < e:
            return True
    return False


# Clearer English than the raw type code gives; everything else is the code in plain words
TYPE_EN = {"japanese_izakaya_restaurant": "Izakaya", "meal_takeaway": "Takeaway", "meal_delivery": "Delivery",
           "bar_and_grill": "Bar & grill", "wine_bar": "Wine bar", "coffee_shop": "Coffee shop"}


def type_en(primary_type: str | None) -> str:
    """English label from Google's primaryType code, e.g. ramen_restaurant -> Ramen restaurant."""
    if not primary_type:
        return "Other"
    return TYPE_EN.get(primary_type) or primary_type.replace("_", " ").capitalize()


def flatten(row) -> dict:
    """One place as a flat record; `row` is a Place or a row with the same columns."""
    p = row.data
    a = regions.area(row.area) if row.area else None
    fnb, fnb_signal = fnb_class(p)
    return {
        "fnb": fnb, "fnb_signal": fnb_signal, "types": p.get("types") or [],
        "pk": row.id, "place_id": row.place_id,
        "name": (p.get("displayName") or {}).get("text", ""),
        "address": p.get("shortFormattedAddress") or p.get("formattedAddress", ""),
        "lat": row.lat, "lng": row.lng, "hex_id": row.hex_id,
        "area": row.area or "outside", "area_jp": a["jp"] if a else "範囲外", "area_en": a["en"] if a else "Outside",
        "type": p.get("primaryType") or "unknown",
        "type_label": type_en(p.get("primaryType")),
        "type_label_jp": (p.get("primaryTypeDisplayName") or {}).get("text") or "",
        "status": p.get("businessStatus") or "UNKNOWN",
        "rating": p.get("rating"), "reviews": p.get("userRatingCount"),
        "price": _price_band(p), "price_level": p.get("priceLevel"), "pay": _pay(p),
        "hours": _intervals(p), "has_hours": bool((p.get("regularOpeningHours") or {}).get("periods")),
        **{k: p.get(k) for k in SERVICES},
        "phone": p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber"),
        "web": p.get("websiteUri"), "photos": len(p.get("photos") or []),
        "maps_uri": p.get("googleMapsUri"), "keywords": row.keywords, "hits": row.hits,
    }


@lru_cache(maxsize=8)
def _frame(run_id: int, unique_places: int) -> pd.DataFrame:
    with session_scope() as db:
        # Streamed in batches: a big run's full Google payloads (~30 KB each) don't fit in memory at once,
        # and only the flattened fields are kept
        q = select(Place.id, Place.place_id, Place.area, Place.hex_id, Place.lat, Place.lng, Place.keywords,
                   Place.hits, Place.data).where(Place.run_id == run_id).execution_options(yield_per=500)
        df = pd.DataFrame([flatten(r) for r in db.execute(q)])
    if df.empty:
        return df
    # Chains: a brand with 3+ branch names ("<brand> <branch>店"), or a name seen 6+ times
    branch = df["name"].str.contains(r"\S+店$", regex=True)
    brand = df["name"].str.replace(r"\s*\S+店$", "", regex=True)
    df["chain"] = (branch & (brand.map(brand[branch].value_counts()).fillna(0) >= 3)) | (
        df["name"].map(df["name"].value_counts()) >= 6)
    df["segment"] = [districts.segment(t, f) for t, f in zip(df["type"], df["fnb"])]
    # The ward a place really lies in. Searches spill over the edge of the selected wards, so places
    # outside the selection get their own ward (e.g. Namba -> Chuo) instead of "Outside"
    out = df["area"] == "outside"
    df["ward"] = df["area"]
    if out.any():
        df.loc[out, "ward"] = regions.locate_many(df.loc[out, "lat"].tolist(), df.loc[out, "lng"].tolist())
    df["ward_en"] = [a if not o else regions.area_name(w) for a, o, w in zip(df["area_en"], out, df["ward"])]
    df["ward_selected"] = ~out
    df["district"], df["district_jp"] = districts.assign(df["lat"], df["lng"], df["ward_en"])
    return df


def frame(run_id: int) -> pd.DataFrame:
    """Cached per run; the key includes the place count so a live run is re-read as it grows."""
    with session_scope() as db:
        run = db.get(Run, run_id)
        n = run.unique_places if run else 0
    return _frame(run_id, n)


def default_filters(df: pd.DataFrame) -> dict:
    return {
        "status": ["OPERATIONAL", "CLOSED_TEMPORARILY"], "minRating": 0, "unrated": True, "revIdx": 0,
        "days": list(range(7)), "from": "any", "to": "24:00", "hasHours": False,
        "price": list(range(6)), "pay": list(PAY), "types": [], "svc": [], "qual": [],
        # Places from border cells that fall outside every selected area start excluded
        "areas": sorted(a for a in df["area"].unique().tolist() if a != "outside") if not df.empty else [],
        "fnb": ["core", "related"],
    }


def _hh(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def steps(f: dict) -> list[tuple[str, callable]]:
    any_time = f.get("from", "any") == "any"
    days = f.get("days", list(range(7)))

    def opening(df):
        ok = df["has_hours"] if f.get("hasHours") else pd.Series(True, index=df.index)
        if any_time and len(days) == 7:
            return ok
        w0 = 0 if any_time else _hh(f["from"])
        w1 = 24 * 60 if any_time else _hh(f["to"])
        probes = [d * 1440 + m for d in days for m in range(w0, w1, 30)]
        return ok & df["hours"].map(lambda iv: bool(iv) and any(open_at(iv, x) for x in probes))

    def services(df):
        m = pd.Series(True, index=df.index)
        for k in f.get("svc", []):
            m &= df[k].fillna(False).astype(bool)
        return m

    def quality(df):
        m = pd.Series(True, index=df.index)
        for k in f.get("qual", []):
            m &= {"phone": df["phone"].notna(), "web": df["web"].notna(), "photos": df["photos"] >= 5,
                  "nochain": ~df["chain"]}[k]
        return m

    min_rev = REVIEW_STEPS[min(f.get("revIdx", 0), len(REVIEW_STEPS) - 1)]
    return [
        ("Business status", lambda df: df["status"].isin(f.get("status", []))),
        # Every list is F&B only: places that are not F&B are always dropped here
        ("F&B check", lambda df: df["fnb"].isin([k for k in f.get("fnb", ["core", "related"]) if k != "no"])),
        ("Area", lambda df: df["area"].isin(f.get("areas", []))),
        ("Rating", lambda df: np.where(df["rating"].isna(), bool(f.get("unrated", True)),
                                       df["rating"].fillna(0) >= f.get("minRating", 0))),
        ("Reviews", lambda df: df["reviews"].fillna(0) >= min_rev),
        ("Opening hours", opening),
        ("Price range", lambda df: df["price"].isin(f.get("price", []))),
        ("Payment", lambda df: df["pay"].isin(f.get("pay", []))),
        ("Category", lambda df: df["type"].isin(f["types"]) if f.get("types") else pd.Series(True, index=df.index)),
        ("Services", services),
        ("Contact & quality", quality),
    ]


def apply(df: pd.DataFrame, f: dict) -> tuple[pd.DataFrame, list[dict]]:
    funnel, cur = [], df
    for label, fn in steps(f):
        if cur.empty:
            funnel.append({"l": label, "n": 0, "d": 0})
            continue
        mask = pd.Series(fn(cur), index=cur.index).astype(bool)
        nxt = cur[mask]
        funnel.append({"l": label, "n": len(nxt), "d": len(cur) - len(nxt)})
        cur = nxt
    return cur, funnel
