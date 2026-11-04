"""AI summary of a version profile: Gemini (default) or Claude on Vertex AI, or a rule-based brief in mock mode.

Both produce the same structured brief (headline, key numbers, where / who / when, actions,
watch-outs) so the UI renders one layout; `explain` is the short read shown on the Summary step.
Only aggregate statistics are sent, never raw place JSON.
"""

import json
import logging
import time

from app.services.pricing import llm_usd
from app.settings import get_settings

logger = logging.getLogger(__name__)

SYSTEM = """You are a senior lead-generation analyst for a Japanese bank's merchant-acquiring team \
(card terminals, QR/IC payments, small-business lending). You receive profile statistics of food & \
beverage venues pulled from Google Maps for selected wards, and write a one-screen brief for a \
sales manager deciding where to send field reps this week.

Rules:
- Every claim must cite a number from the data. Prefer counts and percentages over adjectives.
- Rank, don't list: put the highest-yield area / segment first and say why it wins.
- Pitch lines must be concrete and fit the segment (e.g. cash-only izakaya → low-fee terminal + QR).
- Don't restate definitions or describe the charts. No filler like "it is important to".
- Do not use "priority leads", any lead score, or the word "leads"; say merchants or prospects. Count plain things: F&B merchants, merchants reachable
  by phone or website, cash-only / no-card merchants, and cash / no-card merchants with a phone
  (areas[].callable, contact.cash_callable) as the call list.
- Payment info is self-reported and often missing; treat "no payment info" as a lead to verify, not proof of cash-only.
- Use keyword yield and keyword_set: say how many terms cover 90% / 95% of the list (curve), which
  terms add almost nothing once the stronger ones are in (drop, with places lost and cost saved),
  and the duplicate rate (raw hits per unique place).
- Every merchant in the data is F&B (restaurants, bars, cafés, plus F&B-related venues such as night clubs,
  karaoke and cake shops with seating). Groceries, supermarkets and other shops without dine-in are Food
  retail and are left out unless fnb.retail is non-zero. "Merchants" and "F&B merchants" are the same
  number; never contrast them.
- areas[] are wards. Wards with selected=false were only searched along the border of the chosen wards:
  give their counts, never a density, and say they are partly covered.
- Use hotspots (named districts, merchants per km² at the core) for where to send reps, not hex ids.
- areas[].hex says how merchants spread inside a ward: hexes (cells of hex_km2 each), active (hexes with any
  merchant), cover (fewest hexes holding 50 / 80 / 90% of them), hot (hexes in the top 20% / 10% of all
  picked areas' hexes, min = merchants per hex to qualify, share = merchants they hold), dense_share (share in hexes at 1,000+/km²) and
  bands. Use it to say whether a ward is one tight cluster a rep can walk or spread thin; never cite hex ids.
  Use fnb_segments to say which kinds of F&B dominate and which are most cash-reliant.
- Use contact: how many merchants can be phoned or have a website, how many cash-only / no-card
  merchants have a phone (the call list), and contact.web_kinds: own website, group / chain or venue site,
  social media (contact.instagram on Instagram), booking site, gourmet / listing portal. Only own sites and
  social pages reach the merchant directly; a group site reaches head office. There is no email in Google
  data; never claim email reach.
- Write everything in English. Use the English ward names (`en`, e.g. Naniwa, Kita) and English type
  names. Name a search term in English with the Japanese term in brackets, using kw_en, e.g.
  Restaurant (レストラン). Keep merchant names exactly as given. Short sentences."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "takeaway", "kpis", "where", "who", "when", "actions", "caveats"],
    "properties": {
        "headline": {"type": "string", "description": "≤ 12 words, the single most important finding"},
        "takeaway": {"type": "string", "description": "1-2 sentences: what to do and why"},
        "kpis": {"type": "array", "description": "exactly 4", "items": {
            "type": "object", "additionalProperties": False, "required": ["label", "value", "context"],
            "properties": {"label": {"type": "string"}, "value": {"type": "string"}, "context": {"type": "string"}}}},
        "where": {"type": "array", "description": "top 3-4 areas, best first", "items": {
            "type": "object", "additionalProperties": False, "required": ["area", "merchants", "why"],
            "properties": {"area": {"type": "string"}, "merchants": {"type": "integer", "description": "F&B merchants there"},
                           "why": {"type": "string"}}}},
        "who": {"type": "array", "description": "2-3 target segments, best first", "items": {
            "type": "object", "additionalProperties": False, "required": ["segment", "count", "pitch"],
            "properties": {"segment": {"type": "string"}, "count": {"type": "integer"}, "pitch": {"type": "string"}}}},
        "when": {"type": "object", "additionalProperties": False, "required": ["window", "why"],
                 "properties": {"window": {"type": "string"}, "why": {"type": "string"}}},
        "actions": {"type": "array", "description": "3-4 concrete next steps", "items": {"type": "string"}},
        "caveats": {"type": "array", "description": "1-3 data watch-outs", "items": {"type": "string"}},
    },
}


def _prompt_payload(p: dict) -> dict:
    keep = ["rows", "overview", "payment", "segments", "types", "open_peak", "best_visit",
            "visit_window", "completeness", "quality"]
    out = {k: p.get(k) for k in keep}
    out["run"] = {k: p["run"].get(k) for k in ("keywords", "base_res", "max_res", "saturated", "splits")}
    out["areas"] = [{k: v for k, v in a.items() if k not in ("price", "priority_leads", "hex")}
                    | ({"hex": a["hex"] | {"hot": [{k: v for k, v in x.items() if k != "cells"} for x in a["hex"].get("hot", [])]}}
                       if a.get("hex") else {}) for a in p.get("areas", [])[:24]]
    out["segments"] = {k: v for k, v in (p.get("segments") or {}).items() if k != "priority"}
    out["fnb"] = p.get("fnb")
    out["keywords"] = p.get("keywords")
    out["kw_en"] = p.get("kw_en")
    out["type_mix"] = p.get("type_mix")
    out["fnb_segments"] = [{k: v for k, v in s_.items() if k != "types"} | {"types": s_["types"][:5]}
                           for s_ in p.get("fnb_segments") or []]
    out["hotspots"] = [{k: v for k, v in h.items() if k not in ("lat", "lng")} for h in p.get("hotspots") or []]
    if p.get("contact"):
        out["contact"] = {k: v for k, v in p["contact"].items() if k != "email"}
    out["insights"] = p.get("insights")
    if p.get("keyword_set"):
        out["keyword_set"] = {k: v for k, v in p["keyword_set"].items() if k != "per_place_terms"}
    return out


def _llm(system: str, schema: dict, payload: dict, max_tokens: int, effort: str) -> tuple[dict | None, dict]:
    """One structured call to the configured model. Returns (parsed JSON or None if declined, call record)."""
    return (_gemini if get_settings().ai_provider == "gemini" else _claude)(system, schema, payload, max_tokens, effort)


def _vertex_schema(schema: dict) -> dict:
    """JSON schema → Vertex's OpenAPI-style schema (upper-case types, no additionalProperties)."""
    out = {k: v for k, v in schema.items() if k not in ("additionalProperties", "type", "properties", "items")}
    if "type" in schema:
        out["type"] = schema["type"].upper()
    if "properties" in schema:
        out["properties"] = {k: _vertex_schema(v) for k, v in schema["properties"].items()}
    if "items" in schema:
        out["items"] = _vertex_schema(schema["items"])
    return out


def _gemini(system: str, schema: dict, payload: dict, max_tokens: int, effort: str) -> tuple[dict | None, dict]:
    s = get_settings()
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    host = "aiplatform.googleapis.com" if s.gemini_region == "global" else f"{s.gemini_region}-aiplatform.googleapis.com"
    url = (f"https://{host}/v1/projects/{s.gcp_project}/locations/{s.gemini_region}"
           f"/publishers/google/models/{s.gemini_model}:generateContent")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": "Profile statistics (JSON):\n" + json.dumps(payload, ensure_ascii=False)}]}],
        # The model thinks before answering and thinking counts against maxOutputTokens, so leave room
        "generationConfig": {"maxOutputTokens": max_tokens * 4, "temperature": 0.3,
                             "responseMimeType": "application/json", "responseSchema": _vertex_schema(schema)},
    }
    t0 = time.perf_counter()
    r = AuthorizedSession(creds).post(url, json=body, timeout=180)
    r.raise_for_status()
    d = r.json()
    u = d.get("usageMetadata") or {}
    tokens_out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    cand = (d.get("candidates") or [{}])[0]
    reason = cand.get("finishReason", "NONE")
    call = {"mock": False, "status": reason, "tokens_in": u.get("promptTokenCount", 0), "tokens_out": tokens_out,
            "latency_ms": int((time.perf_counter() - t0) * 1000), "cost_usd": llm_usd(u.get("promptTokenCount", 0), tokens_out)}
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
    if reason != "STOP" or not text:
        logger.warning("gemini returned no answer: %s", reason)
        return None, call
    return json.loads(text), call


def _claude(system: str, schema: dict, payload: dict, max_tokens: int, effort: str) -> tuple[dict | None, dict]:
    s = get_settings()
    from anthropic import AnthropicVertex

    client = AnthropicVertex(project_id=s.gcp_project, region=s.vertex_region)
    t0 = time.perf_counter()
    msg = client.messages.create(
        model=s.claude_model,
        max_tokens=max_tokens,
        system=system,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": "Profile statistics (JSON):\n" + json.dumps(payload, ensure_ascii=False)}],
    )
    call = {"mock": False, "status": msg.stop_reason, "tokens_in": msg.usage.input_tokens,
            "tokens_out": msg.usage.output_tokens, "latency_ms": int((time.perf_counter() - t0) * 1000),
            "cost_usd": llm_usd(msg.usage.input_tokens, msg.usage.output_tokens)}
    if msg.stop_reason == "refusal":
        logger.warning("model declined: %s", msg.stop_details)
        return None, call
    return json.loads(next((b.text for b in msg.content if b.type == "text"), "{}")), call


MOCK_CALL = {"mock": True, "status": "OK", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "cost_usd": 0.0}


def summarize(profile: dict, mock: bool) -> tuple[dict, dict]:
    """Returns (summary, call record for billing)."""
    if mock:
        return rule_based(profile), MOCK_CALL
    out, call = _llm(SYSTEM, SCHEMA, _prompt_payload(profile), 4000, "medium")
    if out is None:
        return rule_based(profile) | {"source": "rules (model gave no answer)"}, call
    return out | {"source": get_settings().llm_model}, call


EXPLAIN_SYSTEM = """You brief a sales manager at a Japanese bank's merchant-acquiring team (card terminals, \
QR/IC payments) on a list of food & beverage merchants pulled from Google Maps, before it is saved.
Write a short, plain-English read of the numbers: what is in the list, how reachable it is, how
cash-heavy it is, where it is concentrated, and whether the search was efficient.

Rules:
- Every sentence cites a number from the data. No adjectives without a number.
- Use English ward, district and type names. Name a search term in English with the Japanese term in
  brackets (kw_en). Do not use "priority leads", any lead score, or the word "leads".
- Payment info is self-reported and often missing; say "cash-only or no card info".
- There is no email in Google data; never claim email reach.
- Every merchant in the list is F&B (incl. F&B-related venues); never contrast "merchants" with "F&B merchants".
- Short sentences. No filler, no restating definitions."""

EXPLAIN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "summary", "points"],
    "properties": {
        "headline": {"type": "string", "description": "≤ 14 words, the single most useful finding"},
        "summary": {"type": "string", "description": "2-3 sentences: what this list is and what it means for sales"},
        "points": {"type": "array", "description": "3-5 findings, most useful first", "items": {
            "type": "object", "additionalProperties": False, "required": ["topic", "text"],
            "properties": {"topic": {"type": "string", "description": "1-2 words, e.g. Reach, Cash, Density, Mix, Search"},
                           "text": {"type": "string"}}}},
    },
}


def explain(profile: dict, mock: bool) -> tuple[dict, dict]:
    """Short narrative for the Summary step. Returns (explanation, call record for billing)."""
    if mock:
        return explain_rules(profile), MOCK_CALL
    out, call = _llm(EXPLAIN_SYSTEM, EXPLAIN_SCHEMA, _prompt_payload(profile), 1500, "low")
    if out is None:
        return explain_rules(profile) | {"source": "rules (model gave no answer)"}, call
    return out | {"source": get_settings().llm_model}, call


def explain_rules(p: dict) -> dict:
    """The same shape from the rule-based insights, for mock runs and when the model is unavailable."""
    ins = p.get("insights") or []
    fnb, c = p.get("fnb") or {}, p.get("contact") or {}
    n_fnb = fnb.get("core", {}).get("n", 0) + fnb.get("related", {}).get("n", 0)
    return {
        "headline": f"{n_fnb:,} F&B merchants, {c.get('either_pct', 0):.0f}% reachable by phone or web",
        "summary": f"{p['overview']['cash_or_unknown_pct']}% of operational merchants are cash-only or show no card info; "
                   f"{(c.get('cash_callable') or {}).get('n', 0):,} of them list a phone number.",
        "points": [{"topic": i["k"], "text": i["t"]} for i in ins[:5]],
        "source": "rules (mock)",
    }


PITCH = {
    "card_gap": "First card terminal: free setup and next-day settlement, framed as not losing tourist and card-only customers.",
    "digital_gap": "Bundle payments with a booking/online-presence starter; they answer the phone but have no website.",
}
SEGMENT_NAME = {"card_gap": "Card-acceptance gap", "digital_gap": "Phone-only, no website"}


def kw_name(p: dict, kw: str) -> str:
    """English name with the Japanese search term, e.g. Restaurant (レストラン)."""
    en = (p.get("kw_en") or {}).get(kw)
    return f"{en} ({kw})" if en and en != kw else kw


def rule_based(p: dict) -> dict:
    o, seg, q, pay = p["overview"], p["segments"], p["quality"], p["payment"]
    areas = sorted([a for a in p["areas"] if a.get("selected", a["code"] != "outside")],
                   key=lambda a: -a.get("fnb_n", a["places"]))[:4]
    top = areas[0] if areas else None
    bv = p.get("best_visit")
    peak = p["open_peak"]
    spots = p.get("hotspots") or []
    best_spot = spots[0] if spots else None
    fnb = p.get("fnb") or {}
    contact = p.get("contact") or {}
    callable_ = (contact.get("cash_callable") or {}).get("n", 0)
    fnb_n = fnb.get("core", {}).get("n", 0) + fnb.get("related", {}).get("n", 0)
    kws = p.get("keywords") or []
    weak_kw = [k for k in kws if k["places"] >= 10 and k["only_pct"] < 10]
    ks = p.get("keyword_set") or {}
    drop, drop_total = ks.get("drop") or [], ks.get("drop_total") or {}
    segs = [s_ for s_ in p.get("fnb_segments") or [] if not s_["segment"].startswith("F&B-related")][:3]
    where_go = best_spot["name"] if best_spot else top["en"] if top else None

    return {
        "headline": f"{fnb_n:,} F&B merchants; {callable_:,} cash / no-card ones can be phoned",
        "takeaway": (f"{o['cash_or_unknown_pct']}% of operational venues are cash-only or show no card info. "
                     f"Start in {where_go}, where F&B is densest, and pitch card + QR acceptance." if where_go
                     else "Not enough data to rank areas."),
        "kpis": [
            {"label": "F&B merchants", "value": f"{fnb_n:,}",
             "context": f"incl. {fnb.get('related', {}).get('n', 0):,} F&B-related venues"},
            {"label": "Cash-only / no card info", "value": f"{o['cash_or_unknown_pct']}%",
             "context": f"{pay['cash']['pct']}% explicit cash-only"},
            {"label": "Reachable by phone or web", "value": f"{contact.get('either_pct', o['phone_pct'])}%",
             "context": f"{callable_:,} cash / no-card merchants have a phone"},
            {"label": "Best visit hour", "value": f"{bv['hour']}:00" if bv else "—",
             "context": f"{round(bv['open_share'] * 100)}% open, outside meal rush" if bv else "no hours data"},
        ],
        "where": [{"area": a["en"], "merchants": a.get("fnb_n", a["places"]),
                   "why": f"{a['cash_or_unknown_pct']:.0f}% cash / no card · {a.get('callable', 0):,} to call · "
                          f"{a['per_km2'] or '—'} venues/km²"} for a in areas],
        "who": ([{"segment": s_["segment"], "count": s_["n"],
                  "pitch": (f"{s_['cash_pct']:.0f}% cash / no card: lead with a low-fee terminal + QR."
                            if s_["cash_pct"] >= 50 else
                            f"Mostly card already ({100 - s_['cash_pct']:.0f}%): pitch lower fees and faster settlement.")}
                 for s_ in segs]
                or [{"segment": SEGMENT_NAME[k], "count": seg[k]["n"], "pitch": PITCH[k]}
                    for k in ("card_gap", "digital_gap") if seg[k]["n"]]),
        "when": {"window": f"Weekdays {bv['hour']}:00–{bv['hour'] + 1}:00" if bv else "—",
                 "why": (f"{round(bv['open_share'] * 100)}% of venues are open and past the lunch rush; "
                         f"avoid {peak['day']} {peak['hour']}:00, the busiest hour.") if bv else ""},
        "actions": ([f"Walk {best_spot['name']} ({best_spot['ward']}) first: {best_spot['n']:,} F&B merchants within "
                     f"400 m, {best_spot['cash_pct']:.0f}% cash or no card info."] if best_spot else [])
                   + ([f"Next run, drop {', '.join(kw_name(p, d['keyword']) for d in drop[:4])}: together they add "
                       f"{drop_total['places_lost']:,} places for {drop_total['calls']:,} calls (≈ {get_settings().currency} {drop_total['saves_local']:,.0f})."]
                      if drop else [f"Drop or merge {', '.join(kw_name(p, k['keyword']) for k in weak_kw[:3])}: under 10% of their places "
                                    "were not already found by other terms."] if weak_kw else [])
                   + [f"Call the {callable_:,} cash / no-card merchants that list a phone (Contact slicer → Payment) "
                      "to book visits.",
                      f"Verify payment status on the {pay['none']['n']:,} venues with no payment info during visits."],
        "caveats": [f"{pay['none']['pct']}% have no payment info on Google; confirm on site.",
                    *([f"Venues are concentrated: {', '.join(h['name'] for h in spots[:3])} hold "
                       f"{round(sum(h['share'] for h in spots[:3]))}% of places within 400 m of their cores."]
                      if spots else []),
                    *([f"{ks['terms_for_pct']['95']} of {ks['terms']} terms already cover 95% of the list; "
                       f"each place came back {ks['hits_per_unique']}× on average ({ks['dupe_pct']}% of hits were duplicates)."]
                      if ks.get("hits_per_unique") else []),
                    f"{q['chain_pct']}% look like chains (central purchasing, usually poor fit)."]
                   + ([f"{q['saturated_cells']} cell{'s' if q['saturated_cells'] != 1 else ''} hit the 60-result cap"
                       " even at max resolution; some venues are missing."]
                      if q["saturated_cells"] else []),
        "source": "rules (mock)",
    }
