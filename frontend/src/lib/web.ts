/** What a merchant's website link is (backend app/services/websites.py); "none" = no link. */
export const WEB_KINDS: [string, string, string][] = [
  ["own", "Own website", "#1E1E1C"],
  ["group", "Group / chain site", "#6E685C"],
  ["social", "Social media", "#3E5A63"],
  ["booking", "Booking site", "#B59A5B"],
  ["aggregator", "Gourmet portal", "#A39B88"],
  ["none", "No website", "#C8442B"],
];
export const WEB_LABEL: Record<string, string> = Object.fromEntries(WEB_KINDS.map(([k, l]) => [k, l]));
export const webKind = (r: { web?: string | null; web_kind?: string | null }) => (r.web ? r.web_kind || "own" : "none");
export const isInstagram = (u?: string | null) => !!u && /(^|\.)instagram\.com$/i.test((() => { try { return new URL(u).hostname; } catch { return ""; } })());
