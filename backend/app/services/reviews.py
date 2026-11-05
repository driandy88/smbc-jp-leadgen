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
        "nl": "Dutch", "sv": "Swedish", "pl": "Polish", "ar": "Arabic", "hi": "Hindi", "tr": "Turkish"}


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


def top(g: pd.DataFrame, by: str, n: int = 10) -> list[dict]:
    if g.empty:
        return []
    t = g[g[by] > 0].sort_values([by, "reviews"], ascending=[False, False]).head(n)
    return [_row(r) for r in t.to_dict("records")]


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
            "top_ja": top(g, "est_ja"), "top_en": top(g, "est_en"),
            "by_area": by_col(g, "area"), "by_segment": by_col(g, "segment")[:12]}
