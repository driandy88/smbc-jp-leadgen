"""Review languages: who writes about a merchant on Google, Japanese locals or visitors.

Google returns at most 5 reviews per place (its "most relevant" ones), so the language split is measured on
that sample. Estimated counts scale the sample to the place's full review count:
est. Japanese = total reviews × (Japanese reviews in the sample / sampled reviews with text)."""

from collections import Counter

import pandas as pd

LANG = {"ja": "Japanese", "en": "English", "ko": "Korean", "zh": "Chinese (Simplified)", "zh-Hans": "Chinese (Simplified)",
        "zh-Hant": "Chinese (Traditional)", "zh-TW": "Chinese (Traditional)", "zh-HK": "Chinese (Traditional)",
        "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "tl": "Filipino", "fil": "Filipino",
        "fr": "French", "de": "German", "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
        "nl": "Dutch", "sv": "Swedish", "pl": "Polish", "ar": "Arabic", "hi": "Hindi", "tr": "Turkish",
        "my": "Burmese", "iw": "Hebrew", "he": "Hebrew", "uk": "Ukrainian", "ca": "Catalan", "gn": "Guarani",
        "no": "Norwegian", "nb": "Norwegian", "da": "Danish", "fi": "Finnish", "cs": "Czech", "el": "Greek",
        "hu": "Hungarian", "ro": "Romanian", "fa": "Persian", "ur": "Urdu", "bn": "Bengali", "ne": "Nepali",
        "km": "Khmer", "lo": "Lao", "mn": "Mongolian", "si": "Sinhala", "ta": "Tamil", "sk": "Slovak", "bg": "Bulgarian",
        "hr": "Croatian", "sr": "Serbian", "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian", "sl": "Slovenian"}


def lang_name(code: str | None) -> str:
    if not code:
        return "No text (rating only)"
    return LANG.get(code) or LANG.get(code.split("-")[0]) or code


def group(code: str | None) -> str:
    """Japanese / English / Other for the three-way split."""
    if not code:
        return "None"
    return "Japanese" if code == "ja" else "English" if code.split("-")[0] == "en" else "Other"


def frame(df: pd.DataFrame) -> pd.DataFrame:
    """Merchants with at least one sampled review that has text, with shares and estimated counts."""
    g = df[df["rv_sample"].fillna(0) > 0].copy()
    if g.empty:
        return g
    n = g["rv_sample"].astype(float)
    g["rv_other"] = g["rv_sample"] - g["rv_ja"] - g["rv_en"]
    total = g["reviews"].fillna(0).astype(float)
    for k in ("ja", "en", "other"):
        g[f"share_{k}"] = g[f"rv_{k}"] / n
        g[f"est_{k}"] = (total * g[f"share_{k}"]).round().astype(int)
    g["foreign"] = (g["rv_en"] + g["rv_other"]) > 0
    g["other_langs"] = g["rv_codes"].map(lambda s: ", ".join(
        f"{lang_name(c)}{f' ×{k}' if k > 1 else ''}" for c, k in Counter(x for x in s.split(",") if group(x) == "Other").most_common()))
    return g


def _split(codes: Counter) -> dict:
    n = max(1, sum(codes.values()))
    by = Counter()
    for c, k in codes.items():
        by[group(c)] += k
    return {"ja": by["Japanese"], "en": by["English"], "other": by["Other"], "n": sum(codes.values()),
            "ja_pct": 100 * by["Japanese"] / n, "en_pct": 100 * by["English"] / n, "other_pct": 100 * by["Other"] / n}


def codes(g: pd.DataFrame) -> Counter:
    return Counter(c for s in g["rv_codes"] for c in s.split(",") if c)


def _row(r: dict) -> dict:
    num = lambda x: None if x is None or x != x else x  # noqa: E731
    return {"place_id": r["place_id"], "name": r["name"], "area": r["area"], "segment": r["segment"], "type": r["type_label"],
            "rating": num(r["rating"]), "reviews": int(num(r["reviews"]) or 0), "sample": int(r["rv_sample"]),
            "ja": int(r["rv_ja"]), "en": int(r["rv_en"]), "other": int(r["rv_other"]), "other_langs": r["other_langs"],
            "est_ja": int(r["est_ja"]), "est_en": int(r["est_en"]), "est_other": int(r["est_other"]),
            "pay": r["pay"], "callable": bool(r["callable"]), "maps_uri": r["maps_uri"] if isinstance(r["maps_uri"], str) else None}


# Ways to rank the top list: (sort columns, highest first; ties broken by the ones after the first)
RANKS = {
    "est_ja": ["est_ja", "reviews"], "est_en": ["est_en", "reviews"],
    "ja": ["rv_ja", "est_ja", "reviews"], "en": ["rv_en", "est_en", "reviews"],
    "share_en": ["share_en", "rv_en", "reviews"], "reviews": ["reviews", "rating"], "rating": ["rating", "reviews"],
}
# Ranks by a language only list merchants with at least one review in it
NEEDS = {"est_ja": "rv_ja", "est_en": "rv_en", "ja": "rv_ja", "en": "rv_en", "share_en": "rv_en"}


def top(g: pd.DataFrame, by: str, n: int = 20, min_reviews: int = 0, area: str = "all", callable_only: bool = False) -> dict:
    """The top n merchants by a rank in RANKS, after the filters; total = how many pass the filters."""
    if g.empty:
        return {"rows": [], "total": 0}
    cols = RANKS.get(by) or RANKS["est_ja"]
    t = g[g["reviews"].fillna(0) >= min_reviews]
    if area != "all":
        t = t[t["area"] == area]
    if callable_only:
        t = t[t["callable"]]
    if by in NEEDS:
        t = t[t[NEEDS[by]] > 0]
    t = t.sort_values(cols, ascending=False, na_position="last")
    return {"rows": [_row(r) for r in t.head(n).to_dict("records")], "total": len(t)}


def by_col(g: pd.DataFrame, col: str) -> list[dict]:
    out = []
    for val, x in g.groupby(col, dropna=True):
        s = _split(codes(x))
        out.append({"key": val, "merchants": len(x), "foreign_merchants": int(x["foreign"].sum()),
                    "foreign_pct": 100 * float(x["foreign"].mean()), **s})
    return sorted(out, key=lambda r: -r["merchants"])


def summary(df: pd.DataFrame) -> dict:
    g = frame(df)
    if g.empty:
        return {"covered": 0, "merchants": len(df)}
    c = codes(g)
    langs = [{"code": k, "name": lang_name(k), "n": v} for k, v in c.most_common()]
    return {"covered": len(g), "merchants": len(df), "sampled": int(g["rv_sample"].sum()),
            "total_reviews": int(g["reviews"].fillna(0).sum()), "split": _split(c), "langs": langs,
            "foreign_merchants": int(g["foreign"].sum()),
            "top_ja": top(g, "est_ja")["rows"], "top_en": top(g, "est_en")["rows"],
            "areas": sorted(g["area"].dropna().unique().tolist()), "max_reviews": int(g["reviews"].fillna(0).max()),
            "by_area": by_col(g, "area"), "by_segment": by_col(g, "segment")[:12]}
