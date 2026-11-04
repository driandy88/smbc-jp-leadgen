"""Profile a saved version: the statistics behind the Analysis charts and the AI summary.

Everything is computed from the stored places, so the summary model only ever sees aggregates.
The lead-generation view is aimed at payment and banking sales: cash-only or undeclared payment,
listings with no website, and well-reviewed venues are the signals a sales team acts on.
"""

import math

import h3
import numpy as np
import pandas as pd

from app.services import districts, regions, websites
from app.services.keywords import english_for
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


def _priority(op: pd.DataFrame) -> pd.Series:
    """Priority lead: operational, cash-only or no card info, well reviewed, rated 3.5+, has a phone."""
    rev_med = op["reviews"].median() if len(op) else 0
    return (op["pay"].isin(["cash", "none"]) & (op["reviews"].fillna(0) >= max(rev_med, 10))
            & (op["rating"].fillna(0) >= 3.5) & op["phone"].notna())


POINT_COLS = ["lat", "lng", "name", "type_label", "rating", "reviews", "pay", "fnb", "segment", "district", "area_en", "ward_en", "hex_id",
              "maps_uri", "address", "phone", "web", "web_kind", "status", "price"]


def points(df: pd.DataFrame) -> dict:
    """One row per merchant for the interactive map, as columns plus row arrays to keep the payload small."""
    if df.empty:
        return {"cols": POINT_COLS, "rows": []}
    out = df[df["lat"].notna() & df["lng"].notna()].copy()
    out["lat"], out["lng"] = out["lat"].round(6), out["lng"].round(6)
    out = out[POINT_COLS].astype(object).where(out[POINT_COLS].notna(), None)
    return {"cols": POINT_COLS, "rows": out.values.tolist()}


def profile(df: pd.DataFrame, run: dict, kw_stats: dict[str, dict] | None = None) -> dict:
    """kw_stats: per keyword calls, searches, empty searches, raw hits and unique places for the whole run
    (from the api_calls ledger, before filters)."""
    n = len(df)
    if n == 0:
        return {"rows": 0}
    op = df[df["status"] == "OPERATIONAL"]
    rev_med = op["reviews"].median() if len(op) else 0
    cashish = op["pay"].isin(["cash", "none"])

    # Lead segments (operational only)
    seg_card_gap = op[cashish & (op["reviews"].fillna(0) >= 20)]
    seg_digital_gap = op[op["phone"].notna() & op["web"].isna()]
    seg_priority = op[_priority(op)]
    seg_new = op[op["reviews"].fillna(0) < 10]

    areas = []
    # By the ward each place lies in. Wards outside the selection were only searched along the border,
    # so they get counts but no density
    for code, g in df.groupby("ward"):
        selected = bool(g["ward_selected"].all())
        km2 = regions._km2(regions.area(code)["geom"]) if selected and code != "outside" else None
        gop = g[g["status"] == "OPERATIONAL"]
        areas.append({
            "code": code, "jp": regions.area(code)["jp"] if code != "outside" else "範囲外", "en": g["ward_en"].iloc[0],
            "places": len(g), "selected": selected, "km2": round(km2, 2) if km2 else None,
            "per_km2": round(len(g) / km2, 1) if km2 else None,
            "cash_or_unknown_pct": _pct(gop["pay"].isin(["cash", "none"]).sum(), len(gop)),
            "cash_only_pct": _pct((gop["pay"] == "cash").sum(), len(gop)),
            "median_rating": _median(gop["rating"]), "median_reviews": _median(gop["reviews"]),
            "no_website_pct": _pct(gop["web"].isna().sum(), len(gop)),
            "priority_leads": int(seg_priority["area"].eq(code).sum()),
            "price": [_pct((g["price"] == i).sum(), len(g)) for i in range(6)],
            "top_types": g["type_label"].value_counts().head(6).to_dict(),
            "fnb": {k: int((g["fnb"] == k).sum()) for k in FNB_KEYS},
            "types": _type_rows(g, 8),
            "type_count": int(g["type_label"].nunique()),
            "contact": _contact_counts(g),
            "fnb_n": int((g["fnb"] != "no").sum()),
            "callable": int((gop["pay"].isin(["cash", "none"]) & gop["phone"].notna()).sum()),
            "chains": int(g["chain"].sum()),
            "hex": _area_hex(code, g) if selected and code != "outside" else None,
        })
    areas.sort(key=lambda a: -a["places"])
    _hot_hexes([a["hex"] for a in areas if a["hex"]])

    # Hex maps at the run's base resolution
    base_res = run["base_res"]
    df_hex = df.assign(cell=[h3.geo_to_h3(la, ln, base_res) if pd.notna(la) else None
                             for la, ln in zip(df["lat"], df["lng"])])
    density = df_hex.groupby("cell").size()
    op_hex = df_hex[df_hex["status"] == "OPERATIONAL"].groupby("cell")
    cash_share = op_hex["pay"].apply(lambda s: s.isin(["cash", "none"]).mean())
    cash_n = op_hex.size()
    top_cell = density.idxmax() if len(density) else None
    priority_pks = set(seg_priority["pk"])
    hexes = _hex_table(df_hex, priority_pks, density)

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

    out = {
        "rows": n,
        "run": run,
        "overview": {
            "operational": len(op), "operational_pct": _pct(len(op), n),
            "temp_closed": int((df["status"] == "CLOSED_TEMPORARILY").sum()),
            "perm_closed": int((df["status"] == "CLOSED_PERMANENTLY").sum()),
            "median_rating": _median(op["rating"]), "median_reviews": _median(op["reviews"]),
            "p75_reviews": round(float(op["reviews"].quantile(0.75)), 1) if op["reviews"].notna().any() else None,
            "unrated": int(df["rating"].isna().sum()), "areas": int(df["ward"].nunique()),
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
        "top_leads": [{"name": r["name"], "area": r["area_en"], "type": r["type_label"], "rating": r["rating"],
                       "reviews": int(r["reviews"]) if pd.notna(r["reviews"]) else None, "pay": PAY[r["pay"]],
                       "phone": r["phone"], "maps_uri": r["maps_uri"]} for _, r in leads.iterrows()],
        "areas": areas,
        "rating_hist": _hist(df["rating"].dropna(), RATING_BINS, RATING_LABELS),
        "review_hist": _hist(df["reviews"].fillna(0), REVIEW_BINS, REVIEW_LABELS),
        "price_bands": PRICE_BANDS,
        "types": [{"label": k, "n": int(v), "pct": _pct(v, n)} for k, v in types.head(10).items()],
        "type_by_area": [{"area": a["en"], "shares": {t: _pct(a["top_types"].get(t, 0), a["places"])
                                                      for t in top_type_names}} for a in areas[:9]],
        "top_types": top_type_names,
        "fnb": _fnb(df),
        "type_mix": _type_rows(df, 15),
        "fnb_segments": _fnb_segments(df, op),
        "hotspots": _hotspots(df, op),
        "contact": _contact(df, op),
        "kw_en": {k: english_for(k) or k for k in run.get("keywords") or []},
        "keywords": _keywords(df, kw_stats or {}, run),
        "keyword_set": _keyword_set(df, kw_stats or {}, run),
        "hexes": hexes,
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
    out["insights"] = _insights(out, df, op)
    return out


def _contact_counts(g: pd.DataFrame) -> dict:
    ph, web = g["phone"].notna(), g["web"].notna()
    return {"n": len(g), "phone": int(ph.sum()), "web": int(web.sum()), "either": int((ph | web).sum()),
            "both": int((ph & web).sum()), "neither": int((~ph & ~web).sum())}


def _contact(df: pd.DataFrame, op: pd.DataFrame) -> dict:
    """Ways to reach each merchant. Google Places has phone and website only; there is no email field."""
    n = len(df)
    c = _contact_counts(df)
    ph, web = df["phone"].notna(), df["web"].notna()
    kinds = df["web_kind"]
    hosts = df["web"].map(websites.host)
    split = {"both": c["both"], "phone_only": int((ph & ~web).sum()), "web_only": int((~ph & web).sum()),
             "neither": c["neither"]}
    by_kind = []
    for k, label in websites.KIND.items():
        m = kinds == k
        top = hosts[m].value_counts().head(5) if k != "own" else pd.Series(dtype=int)
        by_kind.append({"k": k, "label": label, "n": int(m.sum()), "pct": _pct(m.sum(), c["web"]),
                        "hosts": [{"host": h, "n": int(v)} for h, v in top.items()]})
    cashish = op[op["pay"].isin(["cash", "none"])]
    fnb_rows = []
    for k in FNB_KEYS:
        g = df[df["fnb"] == k]
        if len(g):
            cc = _contact_counts(g)
            fnb_rows.append({"fnb": k, "n": len(g), "either_pct": _pct(cc["either"], len(g)),
                             "phone_pct": _pct(cc["phone"], len(g)), "web_pct": _pct(cc["web"], len(g))})
    return {
        **c, "either_pct": _pct(c["either"], n), "phone_pct": _pct(c["phone"], n), "web_pct": _pct(c["web"], n),
        "neither_pct": _pct(c["neither"], n),
        "split": {k: {"n": v, "pct": _pct(v, n)} for k, v in split.items()},
        "web_kinds": by_kind,
        "own_site": int((kinds == "own").sum()),
        "instagram": int(df["instagram"].notna().sum()),
        # Reached through a channel the merchant runs itself: phone, own website or social page
        "direct": int((ph | kinds.isin(["own", "social"])).sum()),
        "email": None,
        "cash_callable": {"n": int(cashish["phone"].notna().sum()), "of": len(cashish)},
        "by_fnb": fnb_rows,
    }


def _rate(g: pd.DataFrame) -> dict:
    """Business KPIs for a slice of merchants."""
    n = len(g)
    gop = g[g["status"] == "OPERATIONAL"]
    reach = g["phone"].notna() | g["web"].notna()
    return {"n": n, "reach_pct": _pct(reach.sum(), n), "phone_pct": _pct(g["phone"].notna().sum(), n),
            "cash_pct": _pct(gop["pay"].isin(["cash", "none"]).sum(), len(gop)),
            "median_rating": _median(gop["rating"]), "median_reviews": _median(gop["reviews"]),
            "chains": int(g["chain"].sum())}


def _fnb_segments(df: pd.DataFrame, op: pd.DataFrame) -> list[dict]:
    """What kind of F&B is out there: business segments with their types, reach and cash share."""
    rows = []
    for seg, g in df[df["fnb"] != "no"].groupby("segment"):
        rows.append({"segment": seg, **_rate(g), "pct": _pct(len(g), len(df)),
                     "types": [{"t": t, "n": int(c)} for t, c in g["type_label"].value_counts().items()]})
    return sorted(rows, key=lambda r: (r["segment"].startswith("F&B-related"), -r["n"]))


def _hotspots(df: pd.DataFrame, op: pd.DataFrame) -> list[dict]:
    """Densest F&B neighbourhoods: F&B merchants per km² in a 300 m circle (no grid), named by district."""
    f = df[df["fnb"] != "no"].reset_index(drop=True)
    spots = districts.hotspots(f["lat"], f["lng"])
    if not spots:
        return []
    x, y = districts._xy(f["lat"], f["lng"], float(f["lat"].mean()))
    out = []
    for h in spots:
        near = f[((x - h["_x"]) ** 2 + (y - h["_y"]) ** 2) <= 400 ** 2]
        name = near["district"].mode().iloc[0] if len(near) else f.iloc[h["row"]]["district"]
        jp = near.loc[near["district"] == name, "district_jp"].iloc[0] if len(near) else ""
        out.append({"name": name, "jp": jp, "ward": near["ward_en"].mode().iloc[0] if len(near) else "",
                    "lat": round(h["lat"], 6), "lng": round(h["lng"], 6), "density_km2": h["density_km2"],
                    "core": h["core"], "radius_m": 400, **_rate(near), "share": _pct(len(near), len(f)),
                    "top_segments": [{"s": k, "n": int(v)} for k, v in near["segment"].value_counts().head(3).items()]})
    return out


def _type_rows(g: pd.DataFrame, top: int) -> list[dict]:
    """Merchant types with how many of each are F&B, F&B-related or not; the tail is folded into 'Other'."""
    n = len(g)
    ct = pd.crosstab(g["type_label"], g["fnb"]).reindex(columns=["core", "related", "no"], fill_value=0)
    ct["n"] = ct.sum(axis=1)
    ct = ct.sort_values("n", ascending=False)
    rows = [{"t": t, "n": int(r["n"]), "pct": _pct(r["n"], n), "core": int(r["core"]), "related": int(r["related"]),
             "no": int(r["no"])} for t, r in ct.head(top).iterrows()]
    rest = ct.iloc[top:]
    if len(rest):
        rows.append({"t": f"Other ({len(rest)} types)", "n": int(rest["n"].sum()), "pct": _pct(rest["n"].sum(), n),
                     "core": int(rest["core"].sum()), "related": int(rest["related"].sum()), "no": int(rest["no"].sum()),
                     "other": True})
    return rows


def _insights(p: dict, df: pd.DataFrame, op: pd.DataFrame) -> list[dict]:
    """Plain-language findings from the merchant mix, hotspots and contact data."""
    out = []
    n = p["rows"]
    f, c = p["fnb"], p["contact"]
    areas = [a for a in p["areas"] if a.get("selected", a["code"] != "outside") and a["places"] >= 10]

    out.append({"k": "Mix", "t": f"{n:,} F&B merchants: {pct_s(f['core']['pct'])} restaurants, bars and cafés, "
                                 f"{pct_s(f['related']['pct'])} F&B-related venues (night clubs, karaoke, cake shops with seating)."})

    hs = p.get("hotspots") or []
    if hs:
        top = hs[0]
        t = (f"Densest spot: {top['name']} ({top['ward']}), {top['density_km2']:,} F&B merchants per km² at its core and "
             f"{top['n']:,} within 400 m, {pct_s(top['reach_pct'])} reachable by phone or web.")
        if len(hs) > 1:
            t += (f" Next: {', '.join(h['name'] for h in hs[1:3])}. The top {min(3, len(hs))} spots hold "
                  f"{pct_s(sum(h['share'] for h in hs[:3]))} of all F&B merchants.")
        out.append({"k": "Hotspot", "t": t})

    segs = [s_ for s_ in p.get("fnb_segments") or [] if not s_["segment"].startswith("F&B-related")]
    if len(segs) > 1:
        big_s = segs[0]
        cashy = max((s_ for s_ in segs if s_["n"] >= 20), key=lambda s_: s_["cash_pct"], default=None)
        t = f"Biggest F&B segment: {big_s['segment']} ({big_s['n']:,}, {pct_s(big_s['pct'])} of the list)."
        if cashy and cashy is not big_s:
            t += f" Most cash-reliant: {cashy['segment']}, {pct_s(cashy['cash_pct'])} cash-only or no card info."
        out.append({"k": "Segments", "t": t})

    if areas:
        big = max(areas, key=lambda a: a["places"])
        share = _pct(big["places"], n)
        rate = lambda a, x: _pct(x, a["places"])  # noqa: E731
        lo = min(areas, key=lambda a: rate(a, a["contact"]["either"]))
        hi_r = max(areas, key=lambda a: rate(a, a["contact"]["either"]))
        pure = max(areas, key=lambda a: rate(a, a["fnb"]["core"]))
        mixed = min(areas, key=lambda a: rate(a, a["fnb"]["core"]))
        t = f"{big['en']} holds {big['places']:,} merchants ({pct_s(share)} of the list)."
        # Only call out an area when it really differs from the others
        if rate(pure, pure["fnb"]["core"]) - rate(mixed, mixed["fnb"]["core"]) >= 5:
            t += (f" Purest F&B: {pure['en']} ({pct_s(rate(pure, pure['fnb']['core']))}); most mixed: "
                  f"{mixed['en']} ({pct_s(rate(mixed, mixed['fnb']['core']))}).")
        if rate(hi_r, hi_r["contact"]["either"]) - rate(lo, lo["contact"]["either"]) >= 5:
            t += (f" Hardest to reach: {lo['en']}, only {pct_s(rate(lo, lo['contact']['either']))} have a phone or "
                  f"website, against {pct_s(rate(hi_r, hi_r['contact']['either']))} in {hi_r['en']}.")
        out.append({"k": "Areas", "t": t})

    cc = c["cash_callable"]
    out.append({"k": "Contact", "t": (
        f"{pct_s(c['either_pct'])} can be reached by phone or website; {c['neither']:,} ({pct_s(c['neither_pct'])}) "
        f"have neither and need a walk-in. {cc['n']:,} of {cc['of']:,} cash-only / no-card merchants have a phone: "
        f"that is the call list. Google has no email field.")})

    kinds = {k["k"]: k for k in c["web_kinds"]}
    nonown = kinds["social"]["n"] + kinds["booking"]["n"] + kinds["aggregator"]["n"]
    if c["web"] and _pct(nonown, c["web"]) >= 10:
        top_host = (kinds["aggregator"]["hosts"] or kinds["social"]["hosts"] or kinds["booking"]["hosts"])[0]
        out.append({"k": "Web", "t": (
            f"Of {c['web']:,} website links, {kinds['own']['n']:,} are the merchant's own site, "
            f"{kinds['group']['n']:,} a chain or venue site, {kinds['social']['n']:,} social pages "
            f"({c['instagram']:,} Instagram) and {kinds['booking']['n'] + kinds['aggregator']['n']:,} booking or "
            f"gourmet-portal listings (most often {top_host['host']}). Shops on rented channels are open to a "
            "direct digital / payment offer.")})
    elif c["web"]:
        out.append({"k": "Web", "t": (
            f"{pct_s(c['web_pct'])} have a website and {pct_s(_pct(kinds['own']['n'], c['web']))} of those are the "
            f"merchant's own domain. {c['split']['phone_only']['n']:,} are phone-only: the digital-gap pitch.")})

    if len(areas) > 1:
        ch = max(areas, key=lambda a: a["chains"] / max(1, a["places"]))
        if ch["chains"]:
            out.append({"k": "Chains", "t": (
                f"{ch['en']} has the most chain branches ({pct_s(_pct(ch['chains'], ch['places']))} of its merchants). "
                f"Chains buy centrally, so independents are the realistic field targets there.")})
    return out


def pct_s(v: float) -> str:
    return f"{v:.0f}%"


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


FNB_KEYS = ("core", "related", "retail", "no")


def _fnb(df: pd.DataFrame) -> dict:
    n = len(df)
    out = {k: {"n": int((df["fnb"] == k).sum()), "pct": _pct((df["fnb"] == k).sum(), n)} for k in FNB_KEYS}
    non_core = df[df["fnb"] != "core"]
    out["non_core_types"] = [{"type": t, "n": int(c)} for t, c in non_core["type_label"].value_counts().head(8).items()]
    out["signals"] = {k: int(v) for k, v in df["fnb_signal"].value_counts().items()}
    return out


def _keywords(df: pd.DataFrame, kw_stats: dict[str, dict], run: dict) -> list[dict]:
    """Per search term: coverage of the final list, overlap with other terms, repeats and cost.
    places/only_this/coverage are on the filtered list; hits/repeats/empty come from the whole run."""
    n = len(df)
    rows = df[["pk", "keywords", "fnb", "type_label"]].explode("keywords")
    only = df[df["keywords"].map(len) == 1].assign(kw=lambda d: d["keywords"].str[0])["kw"].value_counts()
    rate = run.get("cost_local", 0) / max(1, run.get("api_calls", 1))
    out = []
    for kw, g in rows.groupby("keywords"):
        st = kw_stats.get(kw, {})
        calls, hits, unique_run = st.get("calls"), st.get("hits", 0), st.get("unique", 0)
        mine = int(only.get(kw, 0))
        out.append({
            "keyword": kw, "places": len(g), "coverage_pct": _pct(len(g), n),
            "only_this": mine, "only_pct": _pct(mine, len(g)), "shared": len(g) - mine,
            "fnb_pct": _pct((g["fnb"] == "core").sum(), len(g)),
            "top_types": g["type_label"].value_counts().head(3).index.tolist(),
            "calls": calls, "searches": st.get("searches"), "empty_pct": _pct(st.get("empty", 0), st.get("searches", 0)),
            "hits": hits, "unique_run": unique_run, "repeats": max(0, hits - unique_run),
            "repeat_pct": _pct(max(0, hits - unique_run), hits), "kept_pct": _pct(len(g), unique_run),
            "per_call": round(hits / calls, 1) if calls else None,
            "cost_local": round(calls * rate, 2) if calls else None,
            "cost_per_unique": round(calls * rate / mine, 2) if calls and mine else None,
        })
    return sorted(out, key=lambda k: -k["places"])


def _keyword_set(df: pd.DataFrame, kw_stats: dict[str, dict], run: dict) -> dict:
    """How the selected terms work together: duplicates, overlap, and the fewest terms that cover the list."""
    n = len(df)
    sets: dict[str, set] = {}
    for pk, kws in zip(df["pk"], df["keywords"]):
        for k in kws:
            sets.setdefault(k, set()).add(pk)
    # Greedy cover: at each step take the term that adds the most places not yet covered
    left, covered, curve = dict(sets), set(), []
    while left:
        k = max(left, key=lambda x: (len(left[x] - covered), -len(curve)))
        gain = len(left.pop(k) - covered)
        covered |= sets[k]
        curve.append({"keyword": k, "gain": gain, "cum": len(covered), "cum_pct": _pct(len(covered), n)})
    need = {str(t): next((i + 1 for i, c in enumerate(curve) if c["cum_pct"] >= t), len(curve)) for t in (80, 90, 95, 100)}

    names = sorted(sets, key=lambda k: -len(sets[k]))
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            both = len(sets[a] & sets[b])
            if both:
                small = min(len(sets[a]), len(sets[b]))
                pairs.append({"a": a, "b": b, "both": both, "of_smaller_pct": _pct(both, small),
                              "jaccard": round(both / len(sets[a] | sets[b]), 3)})
    pairs.sort(key=lambda x: (-x["of_smaller_pct"], -x["both"]))

    # Run-wide duplicates split into re-hits by the same term (overlapping or split cells, extra pages)
    # and places that several terms found
    raw = sum(v.get("hits", 0) for v in kw_stats.values()) or run.get("raw_hits", 0)
    uniq = run.get("unique_places") or 0
    within = sum(max(0, v.get("hits", 0) - v.get("unique", 0)) for v in kw_stats.values())
    cross = max(0, sum(v.get("unique", 0) for v in kw_stats.values()) - uniq)
    rate = run.get("cost_local", 0) / max(1, run.get("api_calls", 1))
    # Tail of the cover curve: terms that add under 1% new places once the stronger terms are in.
    # Unlike "only this", these can be dropped together.
    drop = [{"keyword": c["keyword"], "places_lost": c["gain"], "calls": kw_stats.get(c["keyword"], {}).get("calls"),
             "saves_local": round(kw_stats.get(c["keyword"], {}).get("calls", 0) * rate, 2)}
            for c in curve[1:] if c["gain"] < 0.01 * n]
    counts = df["keywords"].map(len)
    return {
        "terms": len(sets), "places": n, "raw_hits": raw, "unique_run": uniq,
        "dupes": max(0, raw - uniq), "dupe_pct": _pct(max(0, raw - uniq), raw),
        "hits_per_unique": round(raw / uniq, 2) if uniq else None,
        "repeats_same_term": within, "found_by_several": cross,
        "multi_pct": _pct((counts > 1).sum(), n), "avg_terms_per_place": round(float(counts.mean()), 2) if n else 0,
        "per_place_terms": [{"terms": int(k), "places": int(v)} for k, v in counts.value_counts().sort_index().items()],
        "curve": curve, "terms_for_pct": need, "pairs": pairs[:8], "drop": drop,
        "drop_total": {"places_lost": sum(d["places_lost"] for d in drop), "calls": sum(d["calls"] or 0 for d in drop),
                       "saves_local": round(sum(d["saves_local"] for d in drop), 2)},
    }


def _hex_table(df_hex: pd.DataFrame, priority_pks: set, density: pd.Series) -> dict:
    """Per base-resolution hex: merchants, F&B share, type mix, cash share, priority leads."""
    rows = []
    for cell, g in df_hex[df_hex["cell"].notna()].groupby("cell"):
        op = g[g["status"] == "OPERATIONAL"]
        rows.append({
            "h": cell, "area": g["area_en"].mode().iloc[0], "places": len(g),
            "fnb": int((g["fnb"] == "core").sum()),
            "related": int((g["fnb"] == "related").sum()),
            "contact": int((g["phone"].notna() | g["web"].notna()).sum()),
            "phone": int(g["phone"].notna().sum()),
            "types": [{"t": t, "n": int(c)} for t, c in g["type_label"].value_counts().head(3).items()],
            "cash_pct": _pct(op["pay"].isin(["cash", "none"]).sum(), len(op)),
            "median_rating": _median(op["rating"]),
            "leads": int(g["pk"].isin(priority_pks).sum()),
        })
    rows.sort(key=lambda r: -r["places"])
    counts = density.sort_values(ascending=False)
    top10 = max(1, round(len(counts) * 0.1))
    fnb = pd.Series([r["fnb"] for r in rows], dtype=float).sort_values(ascending=False)
    cum = fnb.cumsum() / max(1, fnb.sum())
    need = lambda q: int((cum < q).sum()) + 1 if fnb.sum() else 0  # noqa: E731
    return {
        "cells": len(counts),
        "median": float(counts.median()) if len(counts) else 0,
        "p90": float(counts.quantile(0.9)) if len(counts) else 0,
        "max": int(counts.max()) if len(counts) else 0,
        "top10_share": _pct(counts.head(top10).sum(), counts.sum()),
        "top10_cells": top10,
        "fnb_median": float(fnb.median()) if len(fnb) else 0,
        "fnb_max": int(fnb.max()) if len(fnb) else 0,
        "fnb_half_cells": need(0.5), "fnb_80_cells": need(0.8),
        "no_fnb_cells": int((fnb == 0).sum()),
        "dist": _hex_dist(counts, fnb),
        "rows": rows,
        "by_leads": sorted(rows, key=lambda r: -r["leads"])[:5],
    }


HEX_BINS = [0, 1, 2, 5, 10, 20, 50, math.inf]
HEX_LABELS = ["0", "1", "2–4", "5–9", "10–19", "20–49", "50+"]


def _hex_dist(merchants: pd.Series, fnb: pd.Series) -> list[dict]:
    """How many hexes hold 0, 1, 2–4 … merchants, and the same for F&B merchants."""
    cut = lambda s: pd.cut(s, bins=HEX_BINS, labels=HEX_LABELS, right=False).value_counts()  # noqa: E731
    m, f = cut(merchants), cut(fnb)
    return [{"l": l, "merchants": int(m.get(l, 0)), "fnb": int(f.get(l, 0))} for l in HEX_LABELS]


# Area spread is measured on res-9 hexes (~0.1 km², a block a rep can walk) whatever the run searched at:
# base cells (~0.7 km²) are too coarse to show where merchants cluster inside a ward
AREA_HEX_RES = 9
# F&B merchants per km² in a hex
DENSITY_BANDS = [(0, "Empty"), (1, "Sparse · under 200/km²"), (200, "Moderate · 200–999/km²"),
                 (1000, "Dense · 1,000–2,999/km²"), (3000, "Very dense · 3,000+/km²")]


def _area_hex(code: str, g: pd.DataFrame, res: int = AREA_HEX_RES) -> dict:
    """How the area's merchants spread over its hexes: how many hexes, how many have any, and how dense
    each one is. Hexes are the area's cells plus border cells its merchants fall in."""
    km2 = h3.hex_area(res, unit="km^2")
    per = pd.Series([h3.geo_to_h3(la, ln, res) for la, ln in zip(g["lat"], g["lng"]) if pd.notna(la)],
                    dtype=object).value_counts()
    cells = sorted(set(regions.area_hexes(code, res)) | set(per.index))
    per = per.reindex(cells, fill_value=0).sort_values(ascending=False)
    dens = per / km2
    active = per[per > 0]
    cum = per.cumsum() / max(1, per.sum())
    need = lambda q: int((cum < q).sum()) + 1 if len(active) else 0  # noqa: E731  fewest hexes holding q of them
    lo = [b for b, _ in DENSITY_BANDS]
    band = pd.cut(dens, bins=[-1, 0.5, *lo[2:], math.inf], labels=[l for _, l in DENSITY_BANDS]) if len(dens) else dens
    return {
        "res": res, "hex_km2": round(km2, 3), "hexes": len(per), "active": len(active),
        "active_pct": _pct(len(active), len(per)),
        "median_active": float(active.median()) if len(active) else 0,
        "max": int(per.max()) if len(per) else 0, "max_per_km2": round(float(dens.max()), 0) if len(dens) else 0,
        "top_cell": per.index[0] if len(active) else None,
        "half_cells": need(0.5),
        "cover": {"50": need(0.5), "80": need(0.8), "90": need(0.9)},
        "dense_share": float(_pct(per[dens >= 1000].sum(), per.sum())),  # merchants in hexes at 1,000+/km²
        "bands": [{"l": l, "hexes": int((band == l).sum()), "merchants": int(per[band == l].sum())}
                  for _, l in DENSITY_BANDS],
        "counts": [(c, int(n)) for c, n in per.items()],  # read by _hot_hexes, then dropped
    }


def _hot_hexes(hexes: list[dict]) -> None:
    """Hot hexes per area: hexes in the top 20% / 10% of all picked areas' hexes by merchants. One cutoff for
    every area, so the counts compare areas (a cutoff inside one area always marks ~20% / 10% of its hexes)."""
    every = pd.Series([n for h in hexes for _, n in h["counts"]], dtype=float)
    for h in hexes:
        counts = h.pop("counts")
        c = pd.Series([n for _, n in counts], index=[k for k, _ in counts], dtype=float)
        h["hot"] = []
        for top, q in (("20", 0.8), ("10", 0.9)):
            cut = float(every.quantile(q)) if len(every) else 0
            m = c >= max(cut, 1)
            h["hot"].append({"top": top, "min": round(cut), "pool": len(every), "hexes": int(m.sum()),
                             "share": _pct(c[m].sum(), c.sum()),
                             "cells": [{"h": k, "n": int(n)} for k, n in c[m].items()]})  # busiest first
