export const fmt = (n: number | null | undefined) => (n == null ? "—" : Math.round(n).toLocaleString("en-US"));
// Display currency comes from the backend config (CURRENCY, default SGD)
let currency = "SGD";
export const setCurrency = (c: string) => { currency = c || currency; };
const SYMBOL: Record<string, string> = { SGD: "S$", USD: "$", JPY: "¥" };
export const money = (n: number | null | undefined) => {
  if (n == null) return "—";
  const digits = currency === "JPY" || Math.abs(n) >= 1000 ? 0 : 2;
  return (SYMBOL[currency] ?? currency + " ") + n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
};
export const pct = (n: number | null | undefined, digits = 1) => (n == null ? "—" : n.toFixed(digits) + "%");

export function elapsed(fromIso: string, toIso?: string | null) {
  const s = Math.max(0, Math.floor(((toIso ? Date.parse(toIso) : Date.now()) - Date.parse(fromIso)) / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

// Server timestamps from SQLite come back without a zone; they are UTC
export const utc = (iso: string) => (/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");

export function shortDate(iso: string) {
  const d = new Date(utc(iso));
  return d.toLocaleDateString("en-CA", { timeZone: "Asia/Tokyo" });
}

export function timeOf(iso: string) {
  return new Date(utc(iso)).toLocaleTimeString("en-GB", { timeZone: "Asia/Tokyo", hour12: false });
}

export const cityName = (key: string) =>
  ({ "osaka-shi": "Osaka", "kyoto-shi": "Kyoto", "sakai-shi": "Sakai", outside: "Outside areas" } as Record<string, string>)[key] || key;
