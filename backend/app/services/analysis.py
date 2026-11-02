"""Profile a saved version: the statistics behind the Analysis charts and the AI summary.

Everything is computed from the stored places, so the summary model only ever sees aggregates.
The lead-generation view is aimed at payment and banking sales: cash-only or undeclared payment,
listings with no website, and well-reviewed venues are the signals a sales team acts on.
"""

import math

import h3
import numpy as np
import pandas as pd

from app.services import regions
from app.services.records import DAYS, PAY, PRICE_BANDS, open_at

RATING_BINS = [0, 2.5, 2.8, 3.1, 3.3, 3.5, 3.7, 3.9, 4.1, 4.3, 5.01]
RATING_LABELS = ["<2.5", "2.5", "2.8", "3.1", "3.3", "3.5", "3.7", "3.9", "4.1", "4.3+"]
REVIEW_BINS = [0, 1, 5, 20, 50, 100, 500, math.inf]
REVIEW_LABELS = ["0", "1–4", "5–19", "20–49", "50–99", "100–499", "500+"]
COMPLETENESS = [("rating", "rating"), ("userRatingCount", "reviews"), ("regularOpeningHours", "has_hours"),
                ("priceRange / priceLevel", "price"), ("paymentOptions", "pay"), ("nationalPhoneNumber", "phone"),
                ("websiteUri", "web"), ("photos", "photos"), ("dineIn", "dineIn"), ("takeout", "takeout"),
                ("reservable", "reservable"), ("servesBeer", "servesBeer")]


def _median(s: pd.Series):
    s = s.dropna()
    return round(float(s.median()), 2) if len(s) else None


def _pct(n: int | float, d: int | float) -> float:
    return round(100 * n / d, 1) if d else 0.0


def profile(df: pd.DataFrame, run: dict) -> dict:
    n = len(df)
    if n == 0:
        return {"rows": 0}
    op = df[df["status"] == "OPERATIONAL"]
    rev_med = op["reviews"].median() if len(op) else 0
    cashish = op["pay"].isin(["cash", "none"])

    # Lead segments (operational only)
    seg_card_gap = op[cashish & (op["reviews"].fillna(0) >= 20)]
    seg_digital_gap = op[op["phone"].notna() & op["web"].isna()]
    seg_priority = op[cashish & (op["reviews"].fillna(0) >= max(rev_med, 10)) & (op["rating"].fillna(0) >= 3.5)
                      & op["phone"].notna()]
    seg_new = op[op["reviews"].fillna(0) < 10]

    areas = []
    for code, g in df.groupby("area"):
        km2 = regions.area(code)["geom"] if code != "outside" else None
        km2 = regions._km2(km2) if km2 is not None else None
        gop = g[g["status"] == "OPERATIONAL"]
        areas.append({
            "code": code, "jp": g["area_jp"].iloc[0], "en": g["area_en"].iloc[0], "places": len(g),
            "per_km2": round(len(g) / km2, 1) if km2 else None,
            "cash_or_unknown_pct": _pct(gop["pay"].isin(["cash", "none"]).sum(), len(gop)),
            "cash_only_pct": _pct((gop["pay"] == "cash").sum(), len(gop)),
            "median_rating": _median(gop["rating"]), "median_reviews": _median(gop["reviews"]),
            "no_website_pct": _pct(gop["web"].isna().sum(), len(gop)),
            "priority_leads": int(seg_priority["area"].eq(code).sum()),
            "price": [_pct((g["price"] == i).sum(), len(g)) for i in range(6)],
            "top_types": g["type_label"].value_counts().head(6).to_dict(),
        })
    areas.sort(key=lambda a: -a["places"])

    # Hex maps at the run's base resolution
    base_res = run["base_res"]
    df_hex = df.assign(cell=[h3.geo_to_h3(la, ln, base_res) if pd.notna(la) else None
                             for la, ln in zip(df["lat"], df["lng"])])
    density = df_hex.groupby("cell").size()
    op_hex = df_hex[df_hex["status"] == "OPERATIONAL"].groupby("cell")
    cash_share = op_hex["pay"].apply(lambda s: s.isin(["cash", "none"]).mean())
    cash_n = op_hex.size()
    top_cell = density.idxmax() if len(density) else None

    # Weekday x hour: share of places with listed hours that are open
    with_hours = op[op["has_hours"]]
    heat = []
    for d in range(7):
        row = []
        for hr in range(24):
            m = d * 1440 + hr * 60 + 30
            row.append(round(float(with_hours["hours"].map(lambda iv, m=m: open_at(iv, m)).mean()), 3)
                       if len(with_hours) else 0)
        heat.append({"d": DAYS[d], "c": row})
    peak = max(((h["d"], i, v) for h in heat for i, v in enumerate(h["c"])), key=lambda x: x[2])
    # Weekday open share by hour. The best visit hour is the one where most places are open
    # outside the lunch (12-13) and dinner (18+) rush, so owners are on site and have time.
    visit = []
    for hr in range(10, 18):
        share = np.mean([heat[d]["c"][hr] for d in range(1, 6)])
        visit.append((hr, round(float(share), 3)))
    calm = [v for v in visit if v[0] not in (12, 13)]
    best_visit = max(calm, key=lambda v: v[1]) if calm else None

    types = df["type_label"].value_counts()
    top_type_names = types.head(6).index.tolist()

    leads = seg_priority.sort_values("reviews", ascending=False).head(15)

    return {
        "rows": n,
        "run": run,
        "overview": {
            "operational": len(op), "operational_pct": _pct(len(op), n),
            "temp_closed": int((df["status"] == "CLOSED_TEMPORARILY").sum()),
            "perm_closed": int((df["status"] == "CLOSED_PERMANENTLY").sum()),
            "median_rating": _median(op["rating"]), "median_reviews": _median(op["reviews"]),
            "p75_reviews": round(float(op["reviews"].quantile(0.75)), 1) if op["reviews"].notna().any() else None,
            "unrated": int(df["rating"].isna().sum()), "areas": int(df["area"].nunique()),
            "types": int(df["type"].nunique()),
            "phone_pct": _pct(op["phone"].notna().sum(), len(op)),
            "no_website_pct": _pct(op["web"].isna().sum(), len(op)),
            "cash_or_unknown_pct": _pct(cashish.sum(), len(op)),
        },
        "payment": {k: {"label": PAY[k], "n": int((op["pay"] == k).sum()), "pct": _pct((op["pay"] == k).sum(), len(op))}
                    for k in PAY},
        "segments": {
            "card_gap": {"n": len(seg_card_gap), "pct": _pct(len(seg_card_gap), len(op)),
                         "def": "Operational, cash-only or no payment info, 20+ reviews"},
            "digital_gap": {"n": len(seg_digital_gap), "pct": _pct(len(seg_digital_gap), len(op)),
                            "def": "Operational, has phone, no website"},
            "priority": {"n": len(seg_priority), "pct": _pct(len(seg_priority), len(op)),
                         "def": f"Cash-only/unknown payment, ≥{int(max(rev_med, 10))} reviews (median), ★3.5+, has phone"},
            "new_or_small": {"n": len(seg_new), "pct": _pct(len(seg_new), len(op)),
                             "def": "Fewer than 10 reviews (new or low-traffic)"},
        },
        "top_leads": [{"name": r["name"], "area": r["area_jp"], "type": r["type_label"], "rating": r["rating"],
                       "reviews": int(r["reviews"]) if pd.notna(r["reviews"]) else None, "pay": PAY[r["pay"]],
                       "phone": r["phone"], "maps_uri": r["maps_uri"]} for _, r in leads.iterrows()],
        "areas": areas,
        "rating_hist": _hist(df["rating"].dropna(), RATING_BINS, RATING_LABELS),
        "review_hist": _hist(df["reviews"].fillna(0), REVIEW_BINS, REVIEW_LABELS),
        "price_bands": PRICE_BANDS,
        "types": [{"label": k, "n": int(v), "pct": _pct(v, n)} for k, v in types.head(10).items()],
        "type_by_area": [{"area": a["jp"], "shares": {t: _pct(a["top_types"].get(t, 0), a["places"])
                                                      for t in top_type_names}} for a in areas[:9]],
        "top_types": top_type_names,
        "density_hex": [{"h": c, "n": int(v)} for c, v in density.items() if c],
        "top_cell": {"h": top_cell, "n": int(density.max())} if top_cell else None,
        "cash_hex": [{"h": c, "share": round(float(cash_share[c]), 3), "n": int(cash_n[c])}
                     for c in cash_share.index if c and cash_n[c] >= 3],
        "open_heat": heat,
        "open_peak": {"day": peak[0], "hour": peak[1], "share": peak[2]},
        "visit_window": [{"hour": h, "open_share": s} for h, s in visit],
        "best_visit": {"hour": best_visit[0], "open_share": best_visit[1]} if best_visit else None,
        "completeness": [{"field": label, "pct": _pct(_filled(df, col), n)} for label, col in COMPLETENESS],
        "quality": {
            "perm_closed_pct": _pct((df["status"] == "CLOSED_PERMANENTLY").sum(), n),
            "no_hours_pct": _pct((~df["has_hours"]).sum(), n),
            "outside_areas": int((df["area"] == "outside").sum()),
            "chain_pct": _pct(df["chain"].sum(), n),
            "multi_keyword_pct": _pct((df["keywords"].map(len) > 1).sum(), n),
            "duplicates_merged": run.get("raw_hits", 0) - run.get("unique_places", 0),
            "saturated_cells": run.get("saturated", 0),
        },
    }


def _filled(df: pd.DataFrame, col: str) -> int:
    if col == "price":
        return int((df["price"] != 5).sum())
    if col == "pay":
        return int((df["pay"] != "none").sum())
    if col == "photos":
        return int((df["photos"] > 0).sum())
    if col == "has_hours":
        return int(df["has_hours"].sum())
    return int(df[col].notna().sum())


def _hist(s: pd.Series, bins, labels) -> list[dict]:
    counts = pd.cut(s, bins=bins, labels=labels, right=False).value_counts().reindex(labels, fill_value=0)
    return [{"l": l, "v": int(v)} for l, v in counts.items()]
