"""AI summary of a version profile: Claude Sonnet on Vertex AI, or a rule-based brief in mock mode.

Both produce the same structured brief (headline, key numbers, where / who / when, actions,
watch-outs) so the UI renders one layout. Only aggregate statistics are sent (plus the top-lead
names already shown in the UI), never raw place JSON.
"""

import json
import logging
import time

from app.services.pricing import claude_usd
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
- Payment info is self-reported and often missing; treat "no payment info" as a lead to verify, not proof of cash-only.
- Use the hex data: name the 1-2 hexes (by ward + hex id) a rep should walk first, and say how
  concentrated venues are (share of places in the top 10% of hexes).
- Use keyword yield: call out terms that found few places only they could find (low value per call)
  and terms that found many unique F&B places. Mention the F&B share if non-F&B hits are material.
- Keep Japanese ward and place names as given. English for everything else. Short sentences."""

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
            "type": "object", "additionalProperties": False, "required": ["area", "leads", "why"],
            "properties": {"area": {"type": "string"}, "leads": {"type": "integer"}, "why": {"type": "string"}}}},
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
    out["areas"] = [{k: v for k, v in a.items() if k != "price"} for a in p.get("areas", [])[:24]]
    out["top_leads"] = (p.get("top_leads") or [])[:10]
    out["fnb"] = p.get("fnb")
    out["keywords"] = p.get("keywords")
    if p.get("hexes"):
        h = p["hexes"]
        out["hexes"] = {k: h[k] for k in ("cells", "median", "p90", "max", "top10_share", "top10_cells")}
        out["hexes"]["densest"] = h["rows"][:8]
        out["hexes"]["most_leads"] = h["by_leads"]
    return out


def summarize(profile: dict, mock: bool) -> tuple[dict, dict]:
    """Returns (summary, call record for billing)."""
    if mock:
        return rule_based(profile), {"mock": True, "status": "OK", "tokens_in": 0, "tokens_out": 0,
                                     "latency_ms": 0, "cost_usd": 0.0}
    s = get_settings()
    from anthropic import AnthropicVertex

    client = AnthropicVertex(project_id=s.gcp_project, region=s.vertex_region)
    t0 = time.perf_counter()
    msg = client.messages.create(
        model=s.claude_model,
        max_tokens=4000,
        system=SYSTEM,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content":
                   "Profile statistics (JSON):\n" + json.dumps(_prompt_payload(profile), ensure_ascii=False)}],
    )
    call = {"mock": False, "status": msg.stop_reason, "tokens_in": msg.usage.input_tokens,
            "tokens_out": msg.usage.output_tokens, "latency_ms": int((time.perf_counter() - t0) * 1000),
            "cost_usd": claude_usd(msg.usage.input_tokens, msg.usage.output_tokens)}
    if msg.stop_reason == "refusal":
        logger.warning("summary refused: %s", msg.stop_details)
        return rule_based(profile) | {"source": "rules (model declined)"}, call
    text = next((b.text for b in msg.content if b.type == "text"), "{}")
    return json.loads(text) | {"source": s.claude_model}, call


PITCH = {
    "priority": "Lead with a low-fee card + QR terminal; their reviews show the footfall to justify it.",
    "card_gap": "First card terminal: free setup and next-day settlement, framed as not losing tourist and card-only customers.",
    "digital_gap": "Bundle payments with a booking/online-presence starter; they answer the phone but have no website.",
}
SEGMENT_NAME = {"priority": "Priority leads", "card_gap": "Card-acceptance gap", "digital_gap": "Phone-only, no website"}


def rule_based(p: dict) -> dict:
    o, seg, q, pay = p["overview"], p["segments"], p["quality"], p["payment"]
    areas = [a for a in p["areas"] if a["code"] != "outside"]
    by_leads = sorted(areas, key=lambda a: -a["priority_leads"])[:4]
    top = by_leads[0] if by_leads else None
    bv = p.get("best_visit")
    peak = p["open_peak"]
    lead_share = round(100 * top["priority_leads"] / max(1, seg["priority"]["n"])) if top else 0
    hx = p.get("hexes") or {}
    best_hex = (hx.get("by_leads") or [None])[0]
    fnb = p.get("fnb") or {}
    kws = p.get("keywords") or []
    weak_kw = [k for k in kws if k["places"] >= 10 and k["only_pct"] < 10]

    return {
        "headline": (f"{seg['priority']['n']:,} priority leads in {top['jp']}" if top and len(areas) == 1
                     else f"{seg['priority']['n']:,} priority leads; {top['jp']} holds {lead_share}%" if top
                     else f"{seg['priority']['n']:,} priority leads"),
        "takeaway": (f"{o['cash_or_unknown_pct']}% of operational venues are cash-only or show no card info. "
                     f"Start in {top['jp']} and pitch card + QR acceptance to well-reviewed venues first." if top
                     else "Not enough data to rank areas."),
        "kpis": [
            {"label": "Priority leads", "value": f"{seg['priority']['n']:,}",
             "context": f"{seg['priority']['pct']}% of {o['operational']:,} operational"},
            {"label": "Cash-only / no card info", "value": f"{o['cash_or_unknown_pct']}%",
             "context": f"{pay['cash']['pct']}% explicit cash-only"},
            {"label": "Reachable by phone", "value": f"{o['phone_pct']}%",
             "context": f"{o['no_website_pct']}% have no website"},
            {"label": "Best visit hour", "value": f"{bv['hour']}:00" if bv else "—",
             "context": f"{round(bv['open_share'] * 100)}% open, outside meal rush" if bv else "no hours data"},
        ],
        "where": [{"area": a["jp"], "leads": a["priority_leads"],
                   "why": f"{a['cash_or_unknown_pct']:.0f}% cash/unknown · {a['per_km2'] or '—'} venues/km² · "
                          f"median ★{a['median_rating'] or '—'}"} for a in by_leads if a["priority_leads"]],
        "who": [{"segment": SEGMENT_NAME[k], "count": seg[k]["n"], "pitch": PITCH[k]}
                for k in ("priority", "card_gap", "digital_gap") if seg[k]["n"]],
        "when": {"window": f"Weekdays {bv['hour']}:00–{bv['hour'] + 1}:00" if bv else "—",
                 "why": (f"{round(bv['open_share'] * 100)}% of venues are open and past the lunch rush; "
                         f"avoid {peak['day']} {peak['hour']}:00, the busiest hour.") if bv else ""},
        "actions": ([f"Walk hex {best_hex['h']} ({best_hex['area']}) first: {best_hex['leads']} priority leads among "
                     f"{best_hex['places']} merchants."] if best_hex and best_hex["leads"] else [])
                   + ([f"Drop or merge {', '.join(k['keyword'] for k in weak_kw[:3])}: under 10% of their places were not "
                       "already found by other terms."] if weak_kw else [])
                   + ([f"Assign reps to {', '.join(a['jp'] for a in by_leads[:2])} first ({sum(a['priority_leads'] for a in by_leads[:2]):,} priority leads)."]
                    if by_leads else [])
                   + ["Export the priority segment and call ahead to book visits.",
                      f"Verify payment status on the {pay['none']['n']:,} venues with no payment info during visits."],
        "caveats": [f"{pay['none']['pct']}% have no payment info on Google; confirm on site.",
                    *([f"{round(100 - fnb['core']['pct'], 1)}% of hits are not core F&B "
                       f"(e.g. {', '.join(t['type'] for t in fnb['non_core_types'][:3])}); use the F&B check filter."]
                      if fnb and fnb["core"]["pct"] < 98 else []),
                    *([f"Venues are concentrated: the top {hx['top10_cells']} hexes (10%) hold {hx['top10_share']}% of places."]
                      if hx else []),
                    f"{q['chain_pct']}% look like chains (central purchasing, usually poor fit)."]
                   + ([f"{q['saturated_cells']} cell{'s' if q['saturated_cells'] != 1 else ''} hit the 60-result cap"
                       " even at max resolution; some venues are missing."]
                      if q["saturated_cells"] else []),
        "source": "rules (mock)",
    }
