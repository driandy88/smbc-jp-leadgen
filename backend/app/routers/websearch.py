"""Websites deep dive: a Google Sheet per website class, and the website-finder agent for merchants
whose listing has no website."""

import re
import time
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import AgentPrompt, Run, Version, WebFind, WebSearch
from app.routers.versions import _run_ids, _version_frame
from app.services import gsheets, records, webagent, websites
from app.services.gsheets import Block, Link, Pivot, Report, Table
from app.settings import get_settings

router = APIRouter(prefix="/api", tags=["websites"], dependencies=[Depends(current_user)])

KIND_LABEL = websites.KIND | {"none": "No website"}
MEANS = {
    "own": "Their own site, incl. pages on Wix, gorp.jp, owst.jp: a direct line to the owner.",
    "group": "A chain, operator or venue site (hotel, department store): decisions sit at head office.",
    "social": "Instagram, X, Facebook, LINE as their only link: direct and informal, DM the owner.",
    "portal": "Only a booking page or gourmet portal listing (TableCheck, Tabelog, Hot Pepper…): a rented channel.",
    "none": "No link at all on Google Maps: phone or walk in, or find their site with the agent.",
}
EST_USD = 0.08  # per merchant before any real search has run: found ≈ $0.05, not found ≈ $0.15 (more searches)


def _df(v: Version) -> pd.DataFrame:
    df = _version_frame(v).copy()
    if df.empty:
        raise HTTPException(422, "This version has no rows")
    df["kind"] = df["web_kind"].where(df["web"].notna(), "none").fillna("own")
    df["area"] = df["ward_en"].fillna(df["area_en"])
    df["host"] = df["web"].map(websites.host)
    df["callable"] = (df["status"] == "OPERATIONAL") & df["pay"].isin(["cash", "none"]) & df["phone"].notna()
    return df


def _404():
    raise HTTPException(404, "Not found")


def _v(db: Session, vid: int) -> Version:
    return db.get(Version, vid) or _404()


def _num(x):
    return None if x is None or (isinstance(x, float) and x != x) else x


def _by(g: pd.DataFrame, col: str, base: pd.DataFrame | None, top: int = 20) -> list[list]:
    """Merchants per value of col: count, share (of the same value in base, else of g), call list, cash / no card."""
    out = []
    for val, x in g.groupby(col, dropna=True):
        d = len(base[base[col] == val]) if base is not None else len(g)
        out.append([val, len(x), len(x) / max(1, d), int(x["callable"].sum()), float(x["pay"].isin(["cash", "none"]).mean())])
    return sorted(out, key=lambda r: -r[1])[:top]


def _merchant_rows(g: pd.DataFrame, extra=None) -> tuple[list[str], list[list], list[int]]:
    g = g.sort_values(["callable", "reviews"], ascending=[False, False])
    header = ["Name", "On call list", "Segment", "Type", "Area", "Neighbourhood", "Address", "Phone", "Payment",
              "Rating", "Reviews", "Website", "Site", "Google Maps", "Status"]
    widths = [220, 90, 150, 140, 90, 130, 260, 120, 120, 60, 70, 200, 150, 100, 110]
    rows = []
    for r in g.to_dict("records"):
        rows.append([r["name"], bool(r["callable"]), r["segment"], r["type_label"], r["area"], r["district"], r["address"],
                     r["phone"], records.PAY.get(r["pay"], r["pay"]), _num(r["rating"]), _num(r["reviews"]),
                     Link(r["web"], r["host"] or r["web"]) if isinstance(r["web"], str) else None, r["host"] or None,
                     Link(r["maps_uri"], "Open ↗") if isinstance(r["maps_uri"], str) else None,
                     str(r["status"]).replace("_", " ").title()] + (extra(r) if extra else []))
    return header, rows, widths


def _filename(name: str) -> str:
    """A safe .xlsx file name: no slashes, colons or brackets, words joined by dashes."""
    s = re.sub(r"-{2,}", "-", re.sub(r"[^\w.-]+", "-", name.replace(" · ", "_")))
    return re.sub(r"-?_-?", "_", s).strip("-_") + ".xlsx"


# Workbooks built for a sheet Google wouldn't hold, kept briefly so the .xlsx download that follows doesn't
# build them again: {xlsx path: (time built, name, tabs)}
_BUILT: dict[str, tuple[float, str, list]] = {}
BUILT_TTL = 600


def _cached(xlsx_path: str) -> tuple[str, list] | None:
    """The workbook built for this download a moment ago, used once; None to build it fresh."""
    now = time.time()
    for k in [k for k, v in _BUILT.items() if now - v[0] > BUILT_TTL]:
        _BUILT.pop(k, None)
    hit = _BUILT.pop(xlsx_path, None)
    return hit[1:] if hit else None


def _deliver(name: str, tabs: list, xlsx_path: str) -> dict:
    """A Google Sheet when Drive will hold it; otherwise tell the page to download the same workbook as .xlsx."""
    try:
        return {"url": gsheets.create(name, tabs)}
    except gsheets.Unavailable as e:
        _BUILT[xlsx_path] = (time.time(), name, tabs)
        return {"xlsx": xlsx_path, "filename": _filename(name), "reason": str(e)}


def _xlsx(name: str, tabs: list) -> StreamingResponse:
    fn = _filename(name)
    return StreamingResponse(iter([gsheets.to_xlsx(tabs)]), headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fn)}"},
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/versions/{vid}/sheets/web/{kind}")
def web_sheet(vid: int, kind: str, db: Session = Depends(get_db)):
    """One website class as a Google Sheet: summary pivots, the merchant list, and a live pivot."""
    return _deliver(*_web_tabs(db, vid, kind), f"/api/versions/{vid}/sheets/web/{kind}.xlsx")


@router.get("/versions/{vid}/sheets/web/{kind}.xlsx")
def web_xlsx(vid: int, kind: str, db: Session = Depends(get_db)):
    return _xlsx(*(_cached(f"/api/versions/{vid}/sheets/web/{kind}.xlsx") or _web_tabs(db, vid, kind)))


def _web_tabs(db: Session, vid: int, kind: str) -> tuple[str, list]:
    if kind not in KIND_LABEL:
        raise HTTPException(404, "Unknown website class")
    v = _v(db, vid)
    df = _df(v)
    g = df[df["kind"] == kind]
    if g.empty:
        raise HTTPException(422, "No merchants in this class")
    label, n = KIND_LABEL[kind], len(g)

    extra, ext_head = None, []
    if kind == "none":  # what the website-finder agent found, if it has run
        finds = {f.place_id: f for f in db.scalars(select(WebFind).where(WebFind.version_id == vid, WebFind.status == "done"))}
        if finds:
            ext_head = ["Agent: website exists", "Agent: website"]
            extra = lambda r: ([("Yes" if finds[r["place_id"]].exists else "No"),  # noqa: E731
                                Link(finds[r["place_id"]].website) if finds[r["place_id"]].website else None]
                               if r["place_id"] in finds else [None, None])
    header, rows, widths = _merchant_rows(g, extra)
    header, widths = header + ext_head, widths + [130, 220][:len(ext_head)]
    if kind == "none":  # no link to show
        drop = {header.index("Website"), header.index("Site")}
        header = [h for i, h in enumerate(header) if i not in drop]
        widths = [w for i, w in enumerate(widths) if i not in drop]
        rows = [[x for i, x in enumerate(r) if i not in drop] for r in rows]

    cash_conf = int((g["pay"] == "cash").sum())
    kpis = [(f"{n:,}", label, f"{n / len(df):.0%} of {len(df):,} F&B merchants"),
            (f"{int(g['callable'].sum()):,}", "On the call list", "operating, cash-only or no card info, phone listed"),
            (f"{g['phone'].notna().mean():.0%}", "Have a phone", f"{int(g['phone'].notna().sum()):,} merchants"),
            (f"{cash_conf:,}", "Confirmed cash-only", "say on Google they take no cards")]
    blocks = [
        Block("By area", ["Area", "Merchants", "Share of the area's F&B", "Call list", "Cash / no card"], _by(g, "area", df),
              note="Share = this class as a share of all F&B merchants in that area.", pct_cols=(2, 4), bar_col=1),
        Block("By segment", ["Segment", "Merchants", "Share of this class", "Call list", "Cash / no card"], _by(g, "segment", None),
              pct_cols=(2, 4), bar_col=1),
    ]
    if kind in ("group", "social", "portal"):
        hosts = g["host"].value_counts().head(15)
        blocks.append(Block("Top sites", ["Site", "Merchants", "Share of this class"],
                            [[h, int(c), c / n] for h, c in hosts.items()], pct_cols=(2,), bar_col=1,
                            note="Group: the chain or venue behind the link. Portal: where they rent their presence."))
    dist = g[g["district"].notna()].groupby(["district", "area"]).agg(n=("name", "size"), c=("callable", "sum")).reset_index()
    dist = dist.sort_values("n", ascending=False).head(15)
    blocks.append(Block("Busiest neighbourhoods", ["Neighbourhood", "Area", "Merchants", "Call list"],
                        [[r.district, r.area, int(r.n), int(r.c)] for r in dist.itertuples()],
                        note="Where a rep can meet the most of them in one walk."))

    tabs = [Report(f"{label} · {v.name}", MEANS[kind], blocks, kpis),
            Table("Merchants", header, rows, widths),
            Pivot("Pivot", "Merchants", "Area", "Segment", "Name", note="Live pivot of the Merchants tab: merchants by area × segment. Edit it in the pivot editor.")]
    return f"Hexline · {v.name} · {label} · {datetime.now():%Y-%m-%d %H:%M}", tabs


# ---------------------------------------------------------------- website-finder agent

class NewSearch(BaseModel):
    limit: int = Field(25, ge=1, le=webagent.LIMIT_MAX)
    workers: int = Field(4, ge=1, le=webagent.WORKER_MAX)
    area: str = "all"


def _mock(db: Session, v: Version) -> bool:
    return any(r.mock for r in db.scalars(select(Run).where(Run.id.in_(_run_ids(v)))))


def _candidates(db: Session, v: Version, area: str = "all") -> pd.DataFrame:
    """Operating merchants with no website that no earlier search has answered: call list first, then most reviewed."""
    df = _df(v)
    g = df[(df["kind"] == "none") & (df["status"] == "OPERATIONAL")]
    if area != "all":
        g = g[g["area"] == area]
    seen = set(db.scalars(select(WebFind.place_id).where(WebFind.version_id == v.id, WebFind.status.in_(("queued", "searching", "done")))))
    return g[~g["place_id"].isin(seen)].sort_values(["callable", "reviews"], ascending=[False, False])


def _per_merchant(db: Session) -> float:
    avg = db.scalar(select(func.avg(WebFind.cost_usd)).join(WebSearch).where(WebFind.status == "done", WebSearch.mock.is_(False)))
    return float(avg) if avg else EST_USD


def _search_out(db: Session, ws: WebSearch) -> dict:
    counts = dict(db.execute(select(WebFind.status, func.count()).where(WebFind.search_id == ws.id).group_by(WebFind.status)).all())
    found = db.scalar(select(func.count()).where(WebFind.search_id == ws.id, WebFind.exists.is_(True))) or 0
    s = get_settings()
    return {"id": ws.id, "status": ws.status, "error": ws.error, "created_at": ws.created_at, "finished_at": ws.finished_at,
            "author": ws.author, "mock": ws.mock, "workers": ws.workers, "area": ws.area, "total": ws.total,
            "prompt_version": ws.prompt_version,
            "done": counts.get("done", 0) + counts.get("error", 0) + counts.get("skipped", 0), "errors": counts.get("error", 0),
            "searching": counts.get("searching", 0), "found": found, "cost_local": round(ws.cost_usd * s.usd_rate, 2)}


def _find_out(f: WebFind) -> dict:
    return {"place_id": f.place_id, "name": f.name, "status": f.status, "exists": f.exists, "website": f.website,
            "site_type": f.site_type, "social": f.social, "confidence": f.confidence, "reason": f.reason,
            "queries": f.queries or [], "search_id": f.search_id}


@router.get("/versions/{vid}/websearch")
def websearch_state(vid: int, area: str = "all", db: Session = Depends(get_db)):
    """What the agent can still search, what it has found so far for this version, and its runs."""
    v = _v(db, vid)
    s = get_settings()
    cand = _candidates(db, v, area)
    finds = db.scalars(select(WebFind).where(WebFind.version_id == vid, WebFind.status == "done").order_by(WebFind.id.desc())).all()
    runs = db.scalars(select(WebSearch).where(WebSearch.version_id == vid).order_by(WebSearch.id.desc()).limit(10)).all()
    return {"remaining": len(cand), "remaining_callable": int(cand["callable"].sum()), "mock": _mock(db, v),
            "per_merchant_local": round(_per_merchant(db) * s.usd_rate, 4), "currency": s.currency,
            "workers_max": webagent.WORKER_MAX, "limit_max": webagent.LIMIT_MAX,
            "finds": [_find_out(f) for f in finds], "runs": [_search_out(db, w) for w in runs]}


@router.post("/versions/{vid}/websearch")
def start_websearch(vid: int, body: NewSearch, db: Session = Depends(get_db), user: str = Depends(current_user)):
    v = _v(db, vid)
    if db.scalar(select(func.count()).where(WebSearch.version_id == vid, WebSearch.status.in_(("queued", "running", "cancelling")))):
        raise HTTPException(409, "An agent run is already going for this version")
    cand = _candidates(db, v, body.area).head(body.limit)
    if cand.empty:
        raise HTTPException(422, "Every merchant without a website here has been searched already")
    ws = WebSearch(version_id=vid, author=user, mock=_mock(db, v), workers=body.workers, area=body.area, total=len(cand),
                   prompt_version=webagent.active_prompt(db)[0])
    db.add(ws)
    db.flush()
    db.add_all([WebFind(search_id=ws.id, version_id=vid, place_id=r["place_id"], name=r["name"]) for r in cand.to_dict("records")])
    db.commit()
    webagent.start(ws.id)
    return _search_out(db, ws)


@router.get("/websearch/{sid}")
def websearch_progress(sid: int, db: Session = Depends(get_db)):
    """Progress for the live view: counts, who is being searched now, and the latest answers."""
    ws = db.get(WebSearch, sid) or _404()
    active = db.scalars(select(WebFind).where(WebFind.search_id == sid, WebFind.status == "searching").limit(webagent.WORKER_MAX)).all()
    recent = db.scalars(select(WebFind).where(WebFind.search_id == sid, WebFind.status.in_(("done", "error")))
                        .order_by(WebFind.updated_at.desc()).limit(8)).all()
    return _search_out(db, ws) | {"active": [f.name for f in active], "recent": [_find_out(f) for f in recent]}


@router.post("/websearch/{sid}/cancel")
def cancel_websearch(sid: int, db: Session = Depends(get_db)):
    ws = db.get(WebSearch, sid) or _404()
    if ws.status in ("queued", "running"):
        ws.status = "cancelling"
        db.commit()
    return _search_out(db, ws)


@router.post("/versions/{vid}/sheets/websearch")
def websearch_sheet(vid: int, db: Session = Depends(get_db)):
    """Everything the agent has answered for this version, as a Google Sheet."""
    return _deliver(*_finder_tabs(db, vid), f"/api/versions/{vid}/sheets/websearch.xlsx")


@router.get("/versions/{vid}/sheets/websearch.xlsx")
def websearch_xlsx(vid: int, db: Session = Depends(get_db)):
    return _xlsx(*(_cached(f"/api/versions/{vid}/sheets/websearch.xlsx") or _finder_tabs(db, vid)))


def _finder_tabs(db: Session, vid: int) -> tuple[str, list]:
    v = _v(db, vid)
    finds = {f.place_id: f for f in db.scalars(select(WebFind).where(WebFind.version_id == vid, WebFind.status == "done"))}
    if not finds:
        raise HTTPException(422, "The agent hasn't searched any merchant yet")
    df = _df(v)
    g = df[df["place_id"].isin(finds)].copy()
    g["found"] = g["place_id"].map(lambda p: bool(finds[p].exists))
    g["conf"] = g["place_id"].map(lambda p: finds[p].confidence or "")
    n, yes = len(g), int(g["found"].sum())

    def by(col):
        out = []
        for val, x in g.groupby(col):
            out.append([val, len(x), int(x["found"].sum()), float(x["found"].mean()), int((x["found"] & x["callable"]).sum())])
        return sorted(out, key=lambda r: -r[1])

    conf = g[g["found"]]["conf"].value_counts()
    social = sum(1 for p in g["place_id"] if finds[p].social)
    kpis = [(f"{yes:,}", "Website found", f"of {n:,} merchants searched ({yes / max(1, n):.0%})"),
            (f"{n - yes:,}", "No website", "nothing that really belongs to them"),
            (f"{int(conf.get('high', 0)):,}", "High confidence", "phone or full address matches on the site"),
            (f"{social:,}", "Social account found", "Instagram, LINE, X… (not counted as a website)")]
    blocks = [
        Block("By area", ["Area", "Searched", "Website found", "Found rate", "Found, on call list"], by("area"), pct_cols=(3,), bar_col=2),
        Block("By segment", ["Segment", "Searched", "Website found", "Found rate", "Found, on call list"], by("segment"), pct_cols=(3,), bar_col=2),
        Block("Confidence of the websites found", ["Confidence", "Merchants", "Share"],
              [[k.title(), int(conf.get(k, 0)), conf.get(k, 0) / max(1, yes)] for k in ("high", "medium", "low")], pct_cols=(2,)),
    ]
    prompt_of = dict(db.execute(select(WebSearch.id, WebSearch.prompt_version).where(WebSearch.version_id == vid)).all())
    order = g.sort_values(["found", "callable", "reviews"], ascending=[False, False, False])
    header = ["Name", "Website exists", "Website", "Site type", "Social", "Confidence", "Evidence", "On call list", "Segment",
              "Area", "Neighbourhood", "Address", "Phone", "Google Maps", "Searches the agent ran", "Prompt version"]
    widths = [220, 100, 240, 80, 200, 90, 360, 90, 150, 90, 130, 260, 120, 100, 300, 90]
    rows = []
    for r in order.to_dict("records"):
        f = finds[r["place_id"]]
        rows.append([r["name"], "Yes" if f.exists else "No", Link(f.website) if f.website else None, f.site_type,
                     Link(f.social) if f.social else None, (f.confidence or "").title(), f.reason, bool(r["callable"]),
                     r["segment"], r["area"], r["district"], r["address"], r["phone"],
                     Link(r["maps_uri"], "Open ↗") if isinstance(r["maps_uri"], str) else None, " · ".join(f.queries or []),
                     f"v{prompt_of.get(f.search_id, 0)}"])
    tabs = [Report(f"Website finder · {v.name}",
                   "Merchants whose Google Maps listing shows no website, searched by the AI agent with Google Search. "
                   "Yes = a site that really belongs to the merchant (own or its chain's branch page); portals and social pages don't count.",
                   blocks, kpis),
            Table("Agent results", header, rows, widths),
            Pivot("Pivot", "Agent results", "Area", "Website exists", "Name", note="Live pivot: merchants by area × website found.")]
    return f"Hexline · {v.name} · Website finder · {datetime.now():%Y-%m-%d %H:%M}", tabs


# ---------------------------------------------------------------- agent system prompt, versioned

class NewPrompt(BaseModel):
    text: str = Field(min_length=50, max_length=20000)
    note: str = Field("", max_length=300)


def _prompt_out(p: AgentPrompt) -> dict:
    return {"version": p.version, "text": p.text, "note": p.note, "author": p.author, "created_at": p.created_at}


@router.get("/agent/prompt")
def get_prompt(db: Session = Depends(get_db)):
    """The prompt new runs use, every saved version (newest first), the built-in default and the fixed output rules."""
    version, text = webagent.active_prompt(db)
    rows = db.scalars(select(AgentPrompt).order_by(AgentPrompt.version.desc())).all()
    return {"version": version, "text": text, "default": webagent.DEFAULT_PROMPT, "output_rules": webagent.OUTPUT_RULES,
            "versions": [_prompt_out(p) for p in rows]}


@router.post("/agent/prompt")
def save_prompt(body: NewPrompt, db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Save an edit as the next version; it is used from the next run on. Older versions stay for history and restore."""
    current = webagent.active_prompt(db)[1]
    if body.text.strip() == current.strip():
        raise HTTPException(422, "No changes to save")
    nxt = (db.scalar(select(func.max(AgentPrompt.version))) or 0) + 1
    p = AgentPrompt(version=nxt, text=body.text.strip(), note=body.note.strip(), author=user)
    db.add(p)
    db.commit()
    return _prompt_out(p)
