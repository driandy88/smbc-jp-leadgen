"""Feature list: every field Google returns for the version's merchants, ranked by completeness, nested fields
broken down, and a Google Sheet with the full profile."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import Place
from app.routers.websearch import _cached, _deliver, _df, _v, _xlsx
from app.services import features
from app.services.gsheets import Block, Report, Table

router = APIRouter(prefix="/api", tags=["features"], dependencies=[Depends(current_user)])

# A version's merchants don't change once it's made, so its profile is worked out once and saved on the version
# (every server instance reads it from there), plus kept in memory here
_PROFILES: dict[int, dict] = {}
KEEP = 6
SCHEMA = 1  # bump when the profile's shape changes: saved profiles of an older shape are worked out again

ABOUT = ("Every field Google Places returns for the merchants in this version. Completeness = merchants with a value in "
         "the field ÷ all merchants (false counts as a value; empty text, lists and objects don't). Nested fields are "
         "listed by path: a.b is field b inside object a, a[].b is field b inside each item of list a.")


def profile(db: Session, vid: int) -> dict:
    if vid in _PROFILES:
        return _PROFILES[vid]
    v = _v(db, vid)
    out = v.features if v.features and v.features.get("schema") == SCHEMA else None
    if out is None:
        pks = [int(x) for x in _df(v)["pk"]]
        p = features.Profiler()
        for s in range(0, len(pks), 500):
            for (data,) in db.execute(select(Place.data).where(Place.id.in_(pks[s:s + 500]))):
                p.add(data)
        out = features.summary(p.rows(), p.n) | {"schema": SCHEMA}
        v.features = out
        db.commit()
    while len(_PROFILES) >= KEEP:
        _PROFILES.pop(next(iter(_PROFILES)))
    _PROFILES[vid] = out
    return out


@router.get("/versions/{vid}/features")
def feature_list(vid: int, db: Session = Depends(get_db)):
    return profile(db, vid)


@router.post("/versions/{vid}/sheets/features")
def features_sheet(vid: int, db: Session = Depends(get_db)):
    return _deliver(*_tabs(db, vid), f"/api/versions/{vid}/sheets/features.xlsx")


@router.get("/versions/{vid}/sheets/features.xlsx")
def features_xlsx(vid: int, db: Session = Depends(get_db)):
    return _xlsx(*(_cached(f"/api/versions/{vid}/sheets/features.xlsx") or _tabs(db, vid)))


def _top(r: dict, n: int = 5) -> str | None:
    if r["free_text"]:
        return f"Free text, {r['text']['mean']:.0f} characters on average"
    if r["unique"]:
        return f"Different for each merchant, e.g. {r['example']}"
    return " · ".join(f"{v} ({c:,})" for v, c in r["top"][:n]) or None


def _range(r: dict) -> str | None:
    if "num" in r:
        x = r["num"]
        return f"{x['min']:g} – {x['median']:g} – {x['max']:g}"
    if "items" in r:
        return f"{r['items']['mean']:.1f} items on average, up to {r['items']['max']}"
    return None


def _tabs(db: Session, vid: int) -> tuple[str, list]:
    v = _v(db, vid)
    s = profile(db, vid)
    rows, n = s["rows"], s["merchants"]
    top = [r for r in rows if not r["parent"]]
    names = {b["k"]: f"{b['l']} ({b['min']}%+)" if b["min"] else f"{b['l']} (under 10%)" for b in s["band_names"]}
    kpis = [(f"{s['features']:,}", "Features", f"top-level fields Google returns · {n:,} merchants"),
            (f"{s['nested']:,}", "Nested sub-fields", f"inside {s['with_nested']} features that hold objects or lists"),
            (f"{s['usable']:,}", "Usable", "features filled for at least half the merchants"),
            (f"{s['bands']['complete']:,}", "Complete", "features filled for 90%+ of merchants")]

    head = ["#", "Feature", "Field", "Type", "Completeness", "Merchants", "Sub-fields", "Top values"]
    line = lambda i, r: [i, r["label"], r["path"], r["kind"], r["pct"] / 100, r["places"], r["nested"] or None, _top(r)]  # noqa: E731
    others = top[20:]
    blocks = [
        Block("Features by completeness", ["Band", "Features", "Nested sub-fields"],
              [[names[k], s["bands"][k], s["bands_nested"][k]] for k in names], bar_col=1),
        Block("Top 20 features · most complete first", head, [line(i + 1, r) for i, r in enumerate(top[:20])], pct_cols=(4,), bar_col=5),
        Block(f"Others · {len(others)} features", head, [line(i + 21, r) for i, r in enumerate(others)], pct_cols=(4,), bar_col=5,
              note="Filled for fewer merchants. Every field, nested ones too, is on the All fields tab."),
    ]
    for r in [r for r in top if r["children"]][:12]:
        kids = [k for k in rows if k["path"] != r["path"] and k["path"].startswith(r["path"] + (".", "[].")[r["kind"] == "list"])]
        blocks.append(Block(f"Inside {r['label']} · {r['path']}", ["Sub-field", "Field", "Type", "Completeness", "Of merchants with it",
                                                                    "Merchants", "Top values"],
                            [["  " * (k["depth"] - 1) + k["label"], k["path"], k["kind"], k["pct"] / 100, k["pct_parent"] / 100,
                              k["places"], _top(k, 3)] for k in sorted(kids, key=lambda k: k["path"])], pct_cols=(3, 4)))

    all_head = ["Field", "Feature", "Parent", "Level", "Type", "Completeness", "Of parent", "Merchants", "Band", "Sub-fields",
                "Distinct values", "Top values", "Range (min – median – max)", "Example"]
    all_rows = [[r["path"], r["label"], r["parent"], r["depth"] + 1 if r["parent"] else 1, r["kind"], r["pct"] / 100, r["pct_parent"] / 100,
                 r["places"], names[features.band(r["pct"])], r["nested"] or None,
                 f"{r['distinct']:,}+" if r["distinct_capped"] else r["distinct"] or None, _top(r, 8), _range(r),
                 str(r["example"]) if r["example"] is not None else None] for r in rows]
    table = Table("All fields", all_head, all_rows, [260, 200, 200, 50, 70, 100, 80, 80, 140, 80, 90, 420, 200, 260], pct_cols=(5, 6))
    return (f"Hexline · {v.name} · Feature list · {datetime.now():%Y-%m-%d %H:%M}",
            [Report(f"Feature list · {v.name}", ABOUT, blocks, kpis), table])
