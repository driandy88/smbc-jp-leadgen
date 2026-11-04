/** What a merchant's website link is (backend app/services/websites.py); "none" = no link. */
export const WEB_KINDS: [string, string, string][] = [
  ["own", "Own website", "#1E1E1C"],
  ["group", "Group / chain site", "#6E685C"],
  ["social", "Social media", "#3E5A63"],
  ["portal", "Booking / gourmet portal", "#B59A5B"],
  ["none", "No website", "#C8442B"],
];
export const WEB_LABEL: Record<string, string> = Object.fromEntries(WEB_KINDS.map(([k, l]) => [k, l]));
// Analyses saved before booking sites and gourmet portals became one class still say booking / aggregator
const LEGACY: Record<string, string> = { booking: "portal", aggregator: "portal" };
export const webKind = (r: { web?: string | null; web_kind?: string | null }) => (r.web ? LEGACY[r.web_kind || ""] || r.web_kind || "own" : "none");
export const isInstagram = (u?: string | null) => !!u && /(^|\.)instagram\.com$/i.test((() => { try { return new URL(u).hostname; } catch { return ""; } })());
