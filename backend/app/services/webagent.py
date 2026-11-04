"""Website-finder agent: for merchants whose Google Maps listing has no website, search the web and
decide whether a website that really belongs to the merchant exists.

One Gemini call per merchant on Vertex AI with Google Search grounding switched on: the model plans its
own searches (the search skill below), reads the results and answers in JSON. Merchants run in
parallel on a thread pool, `workers` at a time. Every call is written to the api_calls ledger.

Runs in a thread locally, or as a Cloud Run Job (`python -m app.jobs websearch --id N`) in prod, like
a collection run: Cloud Run throttles CPU outside requests.
"""

import json
import logging
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.db import session_scope
from app.models import ApiCall, WebFind, WebSearch
from app.services import websites
from app.settings import get_settings

logger = logging.getLogger(__name__)

SYSTEM = """You are a meticulous web researcher working for a Japanese bank's merchant-acquiring team. \
For one food & beverage merchant in Japan, whose Google Maps listing shows no website, you find out \
whether a website that really belongs to this merchant exists, using the Google Search tool.

## What counts as the merchant's website
- YES, site_type "own": a site run by or for this exact venue: its own domain (e.g. izakaya-hana.jp), or a \
  page on a site builder that is clearly its own (Wix, Jimdo, Peraichi, goope, gorp.jp, owst.jp, \
  sites.google.com, a Google Business Profile site such as *.business.site).
- YES, site_type "group": the official site of the company or chain that operates the venue, but only \
  when it has a page for this exact branch (address or branch name matches), e.g. a chain's store page.
- NOT a website (never answer exists=true for these): Tabelog, Hot Pepper Gourmet, Gurunavi, Retty, \
  Hitosara, TableCheck, Ikyu, OpenTable, Uber Eats, Demae-can, Wolt, TripAdvisor, Yelp, Google Maps, \
  Yahoo! Maps, Mapion, iTown Page, NAVITIME, Ekiten, Jalan, Rakuten, news or blog articles about the venue, \
  job ads (Indeed, Townwork, baitoru), and a building, mall, station or hotel directory page.
- Social media (Instagram, X/Twitter, Facebook, LINE official account, TikTok, Ameblo, note, lit.link, \
  linktr.ee) is NOT a website either. If you find the venue's own social account, put it in `social`, and \
  still answer exists=false unless a real website was also found.

## Search skill: how to search
1. Search the exact name in quotes with the area, e.g. "居酒屋 はな" 北区 天満. Use the Japanese name as given.
2. Search the phone number in both forms, e.g. "06-1234-5678" and 0612345678. A site that lists the same \
   phone number is very strong evidence.
3. If the name has a branch suffix (〜店, 本店, 梅田店), also search the brand without it plus 公式 / \
   ホームページ / 公式サイト, to find a chain or operator site, then look for this branch on it.
4. Try the name in romaji or English if the name is Latin script or the venue looks tourist-facing.
5. Budget: every search costs money. Plan all your queries up front and run them in ONE round of at    most 4 queries (steps 1-3, plus 4 only if relevant). Do not search again to double-check, to look up    social media, or to vary punctuation. If that round finds nothing that matches, the answer is NO.

## How to decide
- Verify identity before you answer YES: the site must match at least two of: name (allowing for \
  katakana / kanji / romaji variants), address or neighbourhood, phone number, type of cuisine.
- Watch for namesakes: many venues share a name across Japan. A same-name restaurant in another city is \
  a different merchant. When unsure, answer NO.
- A closed or parked domain, or a site that clearly belongs to a different business, is NO.
- Only give a URL you saw in the search results. Never guess or construct a URL. Give the homepage or the \
  branch page, not a deep link to a menu image.
- confidence: "high" when the phone number or full address matches on the site; "medium" when name and \
  area match but nothing more; "low" otherwise. A YES with low confidence should usually be NO.

## Output
Answer with ONLY one JSON object, no prose and no code fences:
{"exists": true|false, "website": "https://..." or "", "site_type": "own"|"group"|"", \
"social": "https://..." or "", "confidence": "high"|"medium"|"low", \
"reason": "one short English sentence citing the evidence, e.g. 'Own domain lists the same phone 06-…'"}
When exists is false, website and site_type are empty strings."""

WORKER_MAX = 16
LIMIT_MAX = 2000


def _merchant_text(m: dict) -> str:
    keys = [("Name", "name"), ("Type", "type_label"), ("Address", "address"), ("Phone", "phone"),
            ("Neighbourhood", "district"), ("Ward", "ward_en"), ("Google Maps", "maps_uri"),
            ("Rating", "rating"), ("Reviews", "reviews")]
    lines = [f"{label}: {m[k]}" for label, k in keys if m.get(k) not in (None, "")]
    return "Merchant (from its Google Maps listing, which shows no website):\n" + "\n".join(lines)


def _parse(text: str) -> dict:
    """The JSON object in the reply, tolerant of code fences or a sentence around it."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in reply")
    return json.loads(m.group(0))


def _clean(d: dict) -> dict:
    """Hold the answer to the rules: a portal or social link is never the website."""
    url = (d.get("website") or "").strip()
    social = (d.get("social") or "").strip()
    ok = bool(d.get("exists")) and url.startswith(("http://", "https://"))
    kind = websites.listed_kind(url) if ok else None
    if kind == "social":
        social, ok = social or url, False
    elif kind == "portal":
        ok = False
    conf = d.get("confidence") if d.get("confidence") in ("high", "medium", "low") else "low"
    return {"exists": ok, "website": url if ok else None,
            "site_type": (d.get("site_type") if d.get("site_type") in ("own", "group") else "own") if ok else None,
            "social": social if social.startswith(("http://", "https://")) else None,
            "confidence": conf, "reason": (d.get("reason") or "")[:500]}


def search_one(m: dict) -> tuple[dict, dict]:
    """Ask Gemini, with Google Search, about one merchant. Returns (answer, call record)."""
    s = get_settings()
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    host = "aiplatform.googleapis.com" if s.gemini_region == "global" else f"{s.gemini_region}-aiplatform.googleapis.com"
    url = (f"https://{host}/v1/projects/{s.gcp_project}/locations/{s.gemini_region}"
           f"/publishers/google/models/{s.gemini_model}:generateContent")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": _merchant_text(m)}]}],
        "tools": [{"googleSearch": {}}],
        # Low thinking keeps it from re-searching to double-check; the budget rule in SYSTEM does the rest
        "generationConfig": {"maxOutputTokens": 4096, "temperature": 0, "thinkingConfig": {"thinkingLevel": "LOW"}},
    }
    t0 = time.perf_counter()
    r = None
    for attempt in range(4):  # back off on rate limits
        r = AuthorizedSession(creds).post(url, json=body, timeout=120)
        if r.status_code not in (429, 503):
            break
        time.sleep(2 ** attempt + random.random())
    r.raise_for_status()
    d = r.json()
    u = d.get("usageMetadata") or {}
    cand = (d.get("candidates") or [{}])[0]
    g = cand.get("groundingMetadata") or {}
    queries = g.get("webSearchQueries") or []
    sources = [{"title": c["web"].get("title"), "uri": c["web"].get("uri")} for c in g.get("groundingChunks") or [] if c.get("web")]
    t_in, t_out = u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    cost = t_in / 1e6 * s.gemini_usd_per_mtok_in + t_out / 1e6 * s.gemini_usd_per_mtok_out + len(queries) * s.search_usd_per_1000 / 1000
    call = {"status": cand.get("finishReason", "NONE"), "tokens_in": t_in, "tokens_out": t_out,
            "latency_ms": int((time.perf_counter() - t0) * 1000), "cost_usd": cost}
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
    return _clean(_parse(text)) | {"queries": queries, "sources": sources[:8]}, call


def mock_one(m: dict) -> tuple[dict, dict]:
    """Same shape without calling anything, for mock versions and tests."""
    time.sleep(random.uniform(0.6, 1.8))
    rnd = random.Random(m.get("place_id"))
    yes = rnd.random() < 0.3
    slug = re.sub(r"[^a-z0-9]+", "-", str(m.get("place_id", "x")).lower())[-10:].strip("-") or "shop"
    ans = {"exists": yes, "website": f"https://{slug}.example.jp/" if yes else None, "site_type": "own" if yes else None,
           "social": f"https://www.instagram.com/{slug}/" if not yes and rnd.random() < 0.3 else None,
           "confidence": rnd.choice(["high", "medium"]) if yes else "medium",
           "reason": "Mock: own domain lists the same phone number." if yes else "Mock: only portal listings found.",
           "queries": [f"\"{m.get('name')}\" {m.get('ward_en') or ''}".strip(), str(m.get("phone") or "")],
           "sources": []}
    return ans, {"status": "STOP", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "cost_usd": 0.0}


class Agent:
    """Works through the queued merchants of one search, `workers` at a time."""

    def __init__(self, search_id: int, merchants: dict[str, dict] | None = None):
        self.id = search_id
        self.merchants = merchants  # place_id → listing; loaded from the version when None
        self.lock = threading.Lock()

    def _stopped(self) -> bool:
        with session_scope() as db:
            return db.get(WebSearch, self.id).status in ("cancelling", "cancelled")

    def _listing(self, version_id: int) -> dict[str, dict]:
        from app.db import SessionLocal
        from app.models import Version
        from app.routers.versions import _version_frame

        db = SessionLocal()
        try:
            df = _version_frame(db.get(Version, version_id))
        finally:
            db.close()
        cols = ["place_id", "name", "type_label", "address", "phone", "district", "ward_en", "maps_uri", "rating", "reviews"]
        df = df[cols].astype(object).where(df[cols].notna(), None)
        return {r["place_id"]: r for r in df.to_dict("records")}

    def _one(self, find_id: int, m: dict, mock: bool, version_id: int) -> None:
        if self._stopped():
            return
        with session_scope() as db:
            db.execute(update(WebFind).where(WebFind.id == find_id).values(status="searching", updated_at=datetime.now(timezone.utc)))
        try:
            ans, call = (mock_one if mock else search_one)(m)
            vals = {k: ans[k] for k in ("exists", "website", "site_type", "social", "confidence", "reason", "queries", "sources")}
            vals |= {"status": "done", "cost_usd": call["cost_usd"]}
        except Exception as e:  # noqa: BLE001  one merchant failing must not stop the rest
            logger.warning("web search for %s failed: %s", m.get("place_id"), e)
            vals = {"status": "error", "reason": f"{type(e).__name__}: {str(e)[:200]}", "cost_usd": 0.0}
            call = {"status": f"ERROR:{type(e).__name__}", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "cost_usd": 0.0}
        with session_scope() as db:
            db.execute(update(WebFind).where(WebFind.id == find_id).values(**vals, updated_at=datetime.now(timezone.utc)))
            db.add(ApiCall(version_id=version_id, api="vertex.gemini.search", sku=get_settings().gemini_model, mock=mock,
                           status=call["status"], latency_ms=call["latency_ms"], cost_usd=call["cost_usd"],
                           tokens_in=call["tokens_in"], tokens_out=call["tokens_out"]))
            with self.lock:
                db.execute(update(WebSearch).where(WebSearch.id == self.id).values(cost_usd=WebSearch.cost_usd + call["cost_usd"]))

    def run(self) -> None:
        try:
            with session_scope() as db:
                ws = db.get(WebSearch, self.id)
                if ws.status != "queued":
                    return
                ws.status = "running"
                version_id, mock, workers = ws.version_id, ws.mock, ws.workers
                todo = [(f.id, f.place_id) for f in db.scalars(select(WebFind).where(WebFind.search_id == self.id, WebFind.status == "queued")
                                                                .order_by(WebFind.id))]
            listing = self.merchants or self._listing(version_id)
            with ThreadPoolExecutor(max_workers=max(1, min(WORKER_MAX, workers)), thread_name_prefix=f"websearch-{self.id}") as pool:
                for fid, pid in todo:
                    pool.submit(self._one, fid, listing.get(pid) or {"place_id": pid}, mock, version_id)
            with session_scope() as db:
                ws = db.get(WebSearch, self.id)
                stopped = ws.status == "cancelling"
                if stopped:
                    db.execute(update(WebFind).where(WebFind.search_id == self.id, WebFind.status == "queued").values(status="skipped"))
                ws.status = "cancelled" if stopped else "done"
                ws.finished_at = datetime.now(timezone.utc)
        except Exception as e:  # noqa: BLE001
            logger.exception("web search %s failed", self.id)
            with session_scope() as db:
                ws = db.get(WebSearch, self.id)
                ws.status, ws.error, ws.finished_at = "failed", f"{type(e).__name__}: {e}"[:1000], datetime.now(timezone.utc)


def start(search_id: int) -> str:
    """Thread locally; a Cloud Run Job execution when EXECUTION_MODE=job."""
    s = get_settings()
    if s.execution_mode == "job":
        from google.cloud import run_v2

        client = run_v2.JobsClient()
        name = client.job_path(s.gcp_project, s.gcp_region, s.collect_job_name)
        client.run_job(request=run_v2.RunJobRequest(name=name, overrides=run_v2.RunJobRequest.Overrides(
            container_overrides=[run_v2.RunJobRequest.Overrides.ContainerOverride(
                args=["-m", "app.jobs", "websearch", "--id", str(search_id)])])))
        return "job"
    threading.Thread(target=Agent(search_id).run, name=f"websearch-{search_id}", daemon=True).start()
    return "thread"


def recover_interrupted() -> None:
    """In thread mode a restart kills in-flight searches; mark them so the UI doesn't spin forever."""
    with session_scope() as db:
        ids = [w.id for w in db.scalars(select(WebSearch).where(WebSearch.status.in_(("queued", "running", "cancelling"))))]
        if ids:
            db.execute(update(WebSearch).where(WebSearch.id.in_(ids)).values(status="failed", error="Interrupted by a server restart"))
            db.execute(update(WebFind).where(WebFind.search_id.in_(ids), WebFind.status.in_(("queued", "searching"))).values(status="skipped"))
