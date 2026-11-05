"""Review languages: the Japanese / English / other split of Google reviews, top merchants, and a Google Sheet
with every sampled review."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import Place
from app.routers.websearch import _deliver, _df, _num, _v, _xlsx
from app.services import records, reviews
from app.services.gsheets import Block, Link, Pivot, Report, Table

router = APIRouter(prefix="/api", tags=["reviews"], dependencies=[Depends(current_user)])

ABOUT = ("Google returns up to 5 of its 'most relevant' reviews per merchant, so the language split is measured on that "
         "sample. Est. counts scale it to the merchant's total reviews: total × share of the sample in that language. "
         "We ask Google in Japanese, and it favours reviews in the asked language, so non-Japanese shares here are a floor.")
TEXT_MAX = 1000


@router.get("/versions/{vid}/reviews")
def review_langs(vid: int, db: Session = Depends(get_db)):
    return reviews.summary(_df(_v(db, vid)))


@router.post("/versions/{vid}/sheets/reviews")
def reviews_sheet(vid: int, db: Session = Depends(get_db)):
    return _deliver(*_tabs(db, vid), f"/api/versions/{vid}/sheets/reviews.xlsx")


@router.get("/versions/{vid}/sheets/reviews.xlsx")
def reviews_xlsx(vid: int, db: Session = Depends(get_db)):
    return _xlsx(*_tabs(db, vid))


def _raw(db: Session, pks: list[int]) -> dict[int, list]:
    """The sampled reviews of each place, read straight from the stored Google payloads."""
    out: dict[int, list] = {}
    for s in range(0, len(pks), 1000):
        for pk, rv in db.execute(select(Place.id, Place.data["reviews"]).where(Place.id.in_(pks[s:s + 1000]))):
            out[pk] = rv or []
    return out


def _top_rows(rows: list[dict]) -> list[list]:
    return [[i + 1, r["name"], r["area"], r["segment"], r["rating"], r["reviews"], f"{r['ja']} / {r['sample']}",
             f"{r['en']} / {r['sample']}", r["est_ja"], r["est_en"], records.PAY.get(r["pay"], r["pay"]),
             Link(r["maps_uri"], "Open ↗") if r["maps_uri"] else None] for i, r in enumerate(rows)]


TOP_HEAD = ["#", "Merchant", "Area", "Segment", "Rating", "Reviews", "Japanese (sample)", "English (sample)",
            "Est. Japanese reviews", "Est. English reviews", "Payment", "Google Maps"]


def _split_rows(rows: list[dict]) -> list[list]:
    return [[r["key"], r["merchants"], r["n"], r["ja_pct"] / 100, r["en_pct"] / 100, r["other_pct"] / 100,
             r["foreign_merchants"], r["foreign_pct"] / 100] for r in rows]


SPLIT_HEAD = ["{}", "Merchants", "Sampled reviews", "Japanese", "English", "Other", "Merchants with a non-Japanese review", "Share of merchants"]


def _tabs(db: Session, vid: int) -> tuple[str, list]:
    v = _v(db, vid)
    df = _df(v)
    g = reviews.frame(df)
    if g.empty:
        raise HTTPException(422, "No review text in this version. Collections from before reviews were stored have none.")
    s = reviews.summary(df)
    sp = s["split"]
    kpis = [(f"{s['covered']:,}", "Merchants with review text", f"of {s['merchants']:,} F&B merchants · {s['sampled']:,} reviews sampled"),
            (f"{sp['ja_pct']:.1f}%", "Japanese", f"{sp['ja']:,} sampled reviews"),
            (f"{sp['en_pct']:.1f}%", "English", f"{sp['en']:,} sampled reviews"),
            (f"{sp['other_pct']:.1f}%", "Other languages", f"{sp['other']:,} sampled reviews"),
            (f"{s['foreign_merchants']:,}", "Have a non-Japanese review", f"{s['foreign_merchants'] / s['covered']:.0%} of merchants with review text")]

    magnets = g[g["callable"] & g["foreign"]].sort_values(["est_en", "est_other", "reviews"], ascending=False).head(15)
    blocks = [
        Block("Languages in the sample", ["Language", "Reviews", "Share"],
              [[x["name"], x["n"], x["n"] / max(1, s["sampled"])] for x in s["langs"]], pct_cols=(2,), bar_col=1,
              note="Language the review was written in, before Google's translation."),
        Block("Top 20 · most Japanese reviews (est.)", TOP_HEAD, _top_rows(s["top_ja"]),
              note="Local favourites: ranked by total reviews × Japanese share of the sample."),
        Block("Top 20 · most English reviews (est.)", TOP_HEAD, _top_rows(s["top_en"]),
              note="Where English-speaking visitors go: ranked by total reviews × English share of the sample."),
        Block("By area", [SPLIT_HEAD[0].format("Area")] + SPLIT_HEAD[1:], _split_rows(s["by_area"]), pct_cols=(3, 4, 5, 7), bar_col=1),
        Block("By segment", [SPLIT_HEAD[0].format("Segment")] + SPLIT_HEAD[1:], _split_rows(reviews.by_col(g, "segment")),
              pct_cols=(3, 4, 5, 7), bar_col=1),
        Block("Visitor magnets on the call list", ["Merchant", "Area", "Segment", "Rating", "Reviews", "Non-Japanese (sample)",
                                                   "Languages", "Payment", "Phone"],
              [[r["name"], r["area"], r["segment"], _num(r["rating"]), _num(r["reviews"]), f"{int(r['rv_en'] + r['rv_other'])} / {int(r['rv_sample'])}",
                ", ".join(x for x in ["English" if r["rv_en"] else "", r["other_langs"]] if x), records.PAY.get(r["pay"], r["pay"]), r["phone"]]
               for r in magnets.to_dict("records")],
              note="Cash-only or no card info, phone listed, and reviewed by visitors: they lose sales to card-carrying tourists."),
    ]

    g = g.sort_values(["est_ja", "reviews"], ascending=False)
    head = ["Merchant", "Area", "Neighbourhood", "Segment", "Type", "Rating", "Reviews", "Sampled reviews", "Japanese", "English",
            "Other", "Other languages", "Japanese share", "English share", "Est. Japanese reviews", "Est. English reviews",
            "Est. other reviews", "Has a non-Japanese review", "Payment", "On call list", "Phone", "Google Maps", "Place ID"]
    rows = [[r["name"], r["area"], r["district"], r["segment"], r["type_label"], _num(r["rating"]), _num(r["reviews"]), int(r["rv_sample"]),
             int(r["rv_ja"]), int(r["rv_en"]), int(r["rv_other"]), r["other_langs"] or None, r["share_ja"], r["share_en"],
             int(r["est_ja"]), int(r["est_en"]), int(r["est_other"]), "Yes" if r["foreign"] else "No",
             records.PAY.get(r["pay"], r["pay"]), "Yes" if r["callable"] else "No", r["phone"],
             Link(r["maps_uri"], "Open ↗") if isinstance(r["maps_uri"], str) else None, r["place_id"]] for r in g.to_dict("records")]
    merchants = Table("Merchants", head, rows, [220, 90, 130, 150, 140, 60, 70, 80, 70, 70, 60, 180, 90, 90, 110, 110, 110, 110, 120, 90, 120, 90, 200],
                      pct_cols=(12, 13))

    raw = _raw(db, [int(x) for x in g["pk"]])
    rrows = []
    for r in g.to_dict("records"):
        for x in raw.get(int(r["pk"]), []):
            code = records.review_lang(x)
            t = (x.get("originalText") or x.get("text") or {}).get("text") or ""
            rrows.append([r["name"], r["area"], r["segment"], reviews.group(code) if code else "No text", reviews.lang_name(code), code,
                          x.get("rating"), (x.get("publishTime") or "")[:10] or None, x.get("relativePublishTimeDescription"),
                          t[:TEXT_MAX] + ("…" if len(t) > TEXT_MAX else "") or None, _num(r["rating"]), _num(r["reviews"]),
                          Link(r["maps_uri"], "Open ↗") if isinstance(r["maps_uri"], str) else None])
    raw_tab = Table("Reviews", ["Merchant", "Area", "Segment", "Language group", "Language", "Code", "Review rating", "Published",
                                "When (Google)", "Review text (original)", "Merchant rating", "Merchant reviews", "Google Maps"],
                    rrows, [220, 90, 150, 110, 150, 60, 80, 90, 100, 420, 90, 100, 90])

    tabs = [Report(f"Review languages · {v.name}", ABOUT, blocks, kpis), merchants, raw_tab,
            Pivot("Pivot · area", "Reviews", "Area", "Language group", "Merchant", label="Reviews",
                  note="Live pivot of the Reviews tab: sampled reviews by area × language. Edit it in the pivot editor."),
            Pivot("Pivot · segment", "Reviews", "Segment", "Language group", "Merchant", label="Reviews",
                  note="Live pivot of the Reviews tab: sampled reviews by segment × language. Edit it in the pivot editor."),
            Pivot("Pivot · language", "Reviews", "Language", "Area", "Merchant", label="Reviews",
                  note="Live pivot of the Reviews tab: each language by area. Edit it in the pivot editor.")]
    return f"Hexline · {v.name} · Review languages · {datetime.now():%Y-%m-%d %H:%M}", tabs
