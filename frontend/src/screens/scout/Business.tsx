import { Fragment, useMemo, useState } from "react";
import type { Points } from "../../components/PlaceMap";
import { fmt, pct } from "../../lib/format";
import { Profile } from "./types";

const Card = ({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) => (
  <div className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
      <span className="lbl">{title}</span>
      {meta && <span className="m" style={{ fontSize: 11, color: "#5E5A52", textAlign: "right" }}>{meta}</span>}
    </div>
    {children}
  </div>
);

/** No frame, for a section embedded in another card. */
const Bare = ({ children }: { title: string; meta?: string; children: React.ReactNode }) => <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>{children}</div>;

const Bar = ({ v, max, c = "#1E1E1C" }: { v: number; max: number; c?: string }) => (
  <span style={{ height: 6, background: "#E2DDD1", display: "block" }}><span style={{ display: "block", height: 6, width: `${(100 * v) / Math.max(1, max)}%`, background: c }} /></span>
);

/** What kind of F&B is out there, in business segments, with reach and cash share per segment. */
export function FnbSegments({ p }: { p: Profile }) {
  const [open, setOpen] = useState<string | null>(null);
  const segs: any[] = p.fnb_segments || [];
  if (!segs.length) return null;
  const core = segs.filter((s) => !s.segment.startsWith("F&B-related"));
  const total = core.reduce((a, s) => a + s.n, 0);
  const max = Math.max(...segs.map((s) => s.n));

  return (
    <Card title="F&B landscape · what kind of venues, and how many" meta={`${fmt(total)} F&B merchants · click a segment for its types`}>
      <div style={{ display: "flex", height: 20, gap: 2 }}>
        {core.map((s, i) => <span key={s.segment} title={`${s.segment} · ${fmt(s.n)}`} style={{ width: `${(100 * s.n) / Math.max(1, total)}%`, background: SEG_C[i % SEG_C.length], minWidth: 3 }} />)}
      </div>
      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 900 }}>
          <div className="m seg-grid" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>SEGMENT</span><span>MERCHANTS</span><span>SHARE</span><span title="phone or website">REACHABLE</span><span title="operational, cash-only or no card info">CASH / NO CARD</span><span>★ MEDIAN</span><span>CHAINS</span><span>MAIN TYPES</span>
          </div>
          {segs.map((s, i) => {
            const isOpen = open === s.segment;
            const related = s.segment.startsWith("F&B-related");
            return (
              <Fragment key={s.segment}>
                <button className="seg-grid mix-row" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : s.segment)} style={{ opacity: related ? 0.7 : 1 }}>
                  <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                    <span style={{ width: 9, height: 9, flex: "0 0 auto", background: related ? "#C9C2B2" : SEG_C[i % SEG_C.length] }} />{isOpen ? "▾" : "▸"} {s.segment}
                  </span>
                  <span style={{ display: "flex", flexDirection: "column", gap: 3 }}><span className="m">{fmt(s.n)}</span><Bar v={s.n} max={max} /></span>
                  <span className="m">{pct(s.pct, 0)}</span>
                  <span className="m" style={{ color: s.reach_pct < 80 ? "#A8371F" : undefined }}>{pct(s.reach_pct, 0)}</span>
                  <span className="m" style={{ color: s.cash_pct >= 60 ? "#C8442B" : undefined }}>{pct(s.cash_pct, 0)}</span>
                  <span className="m">{s.median_rating ?? "—"}</span>
                  <span className="m" style={{ color: "#5E5A52" }}>{fmt(s.chains)}</span>
                  <span style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>{s.types.slice(0, 3).map((t: any) => <span key={t.t} className="type-chip">{t.t} <span className="m">{t.n}</span></span>)}</span>
                </button>
                {isOpen && (
                  <div style={{ padding: "10px 0 14px 18px", background: "#F3F0E8", borderBottom: "1px solid #E2DDD1", display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {s.types.map((t: any) => <span key={t.t} className="type-chip" style={{ fontSize: 12 }}>{t.t} <span className="m">{t.n}</span></span>)}
                  </div>
                )}
              </Fragment>
            );
          })}
        </div>
      </div>
      <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.5 }}>Segments group Google's place types into how a sales team sells. Cash / no card counts operational merchants that are cash-only or list no card payment.</span>
    </Card>
  );
}
const SEG_C = ["#1E1E1C", "#C8442B", "#6E685C", "#A39B88", "#5E7D4A", "#3E5A63", "#D48E78", "#8E9EA3", "#C9C2B2"];

/** The densest neighbourhoods, named, as merchants per km² (no hexes). */
export function Hotspots({ p }: { p: Profile }) {
  const hs: any[] = p.hotspots || [];
  if (!hs.length) return null;
  const max = Math.max(...hs.map((h) => h.density_km2));
  return (
    <Card title="Density · where F&B is most concentrated" meta="F&B merchants per km² in a 300 m core · counts within 400 m">
      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 820 }}>
          <div className="m spot-grid" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>#</span><span>NEIGHBOURHOOD</span><span>F&B / KM²</span><span>F&B MERCHANTS</span><span>REACHABLE</span><span>CASH / NO CARD</span><span>★ MEDIAN</span><span>WHAT'S THERE</span>
          </div>
          {hs.map((h, i) => (
            <div key={i} className="spot-grid" style={{ fontSize: 12, padding: "8px 0", borderBottom: "1px solid #E2DDD1", alignItems: "center" }}>
              <span className="m" style={{ display: "inline-grid", placeItems: "center", width: 18, height: 18, borderRadius: "50%", background: "#C8442B", color: "#F8F6F0", fontSize: 10 }}>{i + 1}</span>
              <span style={{ display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: 14, fontWeight: 500 }}>{h.name}</span>
                <span style={{ fontSize: 11, color: "#8A8478" }}>{h.ward}{h.jp ? <span className="jp"> · {h.jp}</span> : null}</span>
              </span>
              <span style={{ display: "flex", flexDirection: "column", gap: 3 }}><span className="m" style={{ fontSize: 14 }}>{fmt(h.density_km2)}</span><Bar v={h.density_km2} max={max} c="#C8442B" /></span>
              <span className="m">{fmt(h.n)} <span style={{ color: "#8A8478", fontSize: 10 }}>{pct(h.share, 0)}</span></span>
              <span className="m">{pct(h.reach_pct, 0)}</span>
              <span className="m">{pct(h.cash_pct, 0)}</span>
              <span className="m">{h.median_rating ?? "—"}</span>
              <span style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>{h.top_segments.map((s: any) => <span key={s.s} className="type-chip">{s.s} <span className="m">{s.n}</span></span>)}</span>
            </div>
          ))}
        </div>
      </div>
      <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.5 }}>Density counts F&B merchants in a 300 m circle around every F&B merchant, so it follows streets rather than a grid. Names come from the nearest well-known district.</span>
    </Card>
  );
}

type Row = Record<string, any>;
const CLASSES = [
  { k: "both", l: "Phone + website", c: "#1E1E1C" },
  { k: "phone", l: "Phone only", c: "#6E685C" },
  { k: "web", l: "Website only", c: "#A39B88" },
  { k: "none", l: "No contact", c: "#C8442B" },
] as const;
const PAY: Record<string, string> = { cash: "Cash only", none: "No payment info", card: "Card", nfc: "Card + NFC / IC" };
const rating = (r: Row) => (r.rating == null ? "Unrated" : r.rating >= 4.5 ? "★4.5+" : r.rating >= 4 ? "★4.0–4.4" : r.rating >= 3.5 ? "★3.5–3.9" : "Under ★3.5");
const DIMS: { k: string; l: string; f: (r: Row) => string }[] = [
  { k: "segment", l: "F&B segment", f: (r) => r.segment },
  { k: "district", l: "Neighbourhood", f: (r) => r.district },
  { k: "ward", l: "Ward", f: (r) => r.area_en },
  { k: "pay", l: "Payment", f: (r) => PAY[r.pay] || r.pay },
  { k: "rating", l: "Rating", f: rating },
  { k: "type", l: "Place type", f: (r) => r.type_label },
];
const contactClass = (r: Row) => (r.phone && r.web ? "both" : r.phone ? "phone" : r.web ? "web" : "none");

/** Slice the list by contact availability against any business dimension; download any cell as a call list. */
export function ContactSlicer({ points, bare }: { points: Points | null; bare?: boolean }) {
  const [dim, setDim] = useState("segment");
  const [fnbOnly, setFnbOnly] = useState(true);
  const [sel, setSel] = useState<{ row: string | null; cls: string | null } | null>(null);
  const [all, setAll] = useState(false);

  const rows = useMemo<Row[]>(() => (points ? points.rows.map((r) => Object.fromEntries(points.cols.map((c, i) => [c, r[i]]))) : []), [points]);
  const d = DIMS.find((x) => x.k === dim)!;
  const base = useMemo(() => (fnbOnly ? rows.filter((r) => r.fnb !== "no") : rows), [rows, fnbOnly]);
  const table = useMemo(() => {
    const m = new Map<string, Record<string, number>>();
    for (const r of base) {
      const key = d.f(r) ?? "—";
      const t = m.get(key) || { both: 0, phone: 0, web: 0, none: 0, n: 0 };
      t[contactClass(r)]++;
      t.n++;
      m.set(key, t);
    }
    return [...m.entries()].sort((a, b) => b[1].n - a[1].n);
  }, [base, d]);
  const totals = useMemo(() => {
    const t: Record<string, number> = { both: 0, phone: 0, web: 0, none: 0, n: base.length };
    for (const r of base) t[contactClass(r)]++;
    return t;
  }, [base]);

  const Wrap = bare ? Bare : Card;
  if (!points) return <Wrap title="Contact slicer"><span style={{ fontSize: 12, color: "#5E5A52" }}>Loading merchants…</span></Wrap>;
  const picked = sel ? base.filter((r) => (sel.row == null || d.f(r) === sel.row) && (sel.cls == null || contactClass(r) === sel.cls)) : [];
  const shown = all ? table : table.slice(0, 12);
  const isSel = (row: string | null, cls: string | null) => sel && sel.row === row && sel.cls === cls;
  const cell = (row: string | null, cls: string | null, v: number, n: number, color?: string) => (
    <button className="slice-cell" aria-pressed={!!isSel(row, cls)} disabled={!v} onClick={() => setSel(isSel(row, cls) ? null : { row, cls })} title="Select these merchants">
      <span className="m" style={{ color }}>{fmt(v)}</span><span className="m" style={{ fontSize: 10, color: "#8A8478" }}>{n ? pct((100 * v) / n, 0) : ""}</span>
    </button>
  );

  const download = () => {
    const head = ["name", "segment", "type", "neighbourhood", "ward", "phone", "website", "address", "rating", "reviews", "payment", "google_maps"];
    const q = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = picked.map((r) => [r.name, r.segment, r.type_label, r.district, r.area_en, r.phone, r.web, r.address, r.rating, r.reviews, PAY[r.pay] || r.pay, r.maps_uri].map(q).join(","));
    const blob = new Blob(["﻿" + [head.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `merchants_${(sel?.row || "all").replace(/\W+/g, "-")}_${sel?.cls || "any"}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const selLabel = sel ? [sel.row, sel.cls ? CLASSES.find((c) => c.k === sel.cls)!.l : null].filter(Boolean).join(" · ") || "All merchants" : "";

  return (
    <Wrap title="Contact slicer · who can we reach, by any cut" meta="click a number to select those merchants, then download them">
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", alignItems: "center" }}>
        <span className="lbl" style={{ color: "#5E5A52" }}>Slice by</span>
        <div role="radiogroup" aria-label="Slice by" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {DIMS.map((x) => <button key={x.k} role="radio" className="chip" aria-checked={dim === x.k} aria-pressed={dim === x.k} onClick={() => { setDim(x.k); setSel(null); setAll(false); }}>{x.l}</button>)}
        </div>
        <button className="tog" aria-pressed={fnbOnly} onClick={() => { setFnbOnly(!fnbOnly); setSel(null); }} style={{ marginLeft: "auto" }}><span className="trk"><span className="knob" /></span>F&B only</button>
      </div>

      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 760 }}>
          <div className="m slice-grid" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>{d.l.toUpperCase()}</span><span>MERCHANTS</span>
            {CLASSES.map((c) => <span key={c.k} style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><span style={{ width: 8, height: 8, background: c.c }} />{c.l.toUpperCase()}</span>)}
            <span>REACHABLE</span><span>MIX</span>
          </div>
          {[["All", totals] as [string, Record<string, number>], ...shown].map(([key, t], i) => {
            const row = i === 0 ? null : key;
            return (
              <div key={key + i} className="slice-grid" style={{ fontSize: 12, padding: "3px 0", borderBottom: i === 0 ? "1px solid #1E1E1C" : "1px solid #E2DDD1", alignItems: "center", fontWeight: i === 0 ? 600 : 400 }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={key}>{key}</span>
                {cell(row, null, t.n, 0)}
                {CLASSES.map((c) => <Fragment key={c.k}>{cell(row, c.k, t[c.k], t.n, c.k === "none" && t[c.k] ? "#A8371F" : undefined)}</Fragment>)}
                <span className="m" style={{ color: (100 * (t.n - t.none)) / Math.max(1, t.n) < 80 ? "#A8371F" : undefined }}>{pct((100 * (t.n - t.none)) / Math.max(1, t.n), 0)}</span>
                <span style={{ display: "flex", height: 8, gap: 1 }}>{CLASSES.map((c) => <span key={c.k} style={{ width: `${(100 * t[c.k]) / Math.max(1, t.n)}%`, background: c.c }} />)}</span>
              </div>
            );
          })}
        </div>
      </div>
      {table.length > 12 && <button className="btn2" style={{ alignSelf: "flex-start" }} onClick={() => setAll(!all)}>{all ? "Show top 12" : `Show all ${table.length}`}</button>}

      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", border: "1px solid #1E1E1C", background: "#F3F0E8", padding: "10px 12px", minHeight: 44 }}>
        {sel ? (
          <>
            <span style={{ fontSize: 13 }}><b className="m">{fmt(picked.length)}</b> merchants · {selLabel}{fnbOnly ? " · F&B only" : ""}</span>
            <span style={{ fontSize: 11, color: "#5E5A52", flex: "1 1 200px" }}>{picked.slice(0, 4).map((r) => r.name).join(" · ")}{picked.length > 4 ? " …" : ""}</span>
            <button className="btn" onClick={download}>Download CSV</button>
            <button className="btn2" onClick={() => setSel(null)}>Clear</button>
          </>
        ) : (
          <span style={{ fontSize: 12, color: "#5E5A52" }}>Select a number in the table, e.g. <b>Izakaya & bars × Phone only</b>, to get that call list with names, phone, address and Google Maps link.</span>
        )}
      </div>
    </Wrap>
  );
}

/** Main section: the merchant scorecard with the contact slicer underneath. */
export function MainOverview({ p, points }: { p: Profile; points: Points | null }) {
  const f = p.fnb;
  const c = p.contact;
  if (!f) return null;
  const items = [
    { v: fmt(p.rows), l: "unique merchants", s: `${fmt(p.areas?.length)} areas · ${fmt(p.overview?.types)} types` },
    { v: fmt(f.core.n), l: "F&B", s: pct(f.core.pct), accent: true },
    { v: fmt(f.related.n), l: "F&B-related", s: pct(f.related.pct) },
    { v: fmt(f.no.n), l: "Not F&B", s: pct(f.no.pct) },
    ...(c ? [{ v: pct(c.either_pct, 0), l: "reachable by phone or web", s: `${fmt(c.either)} merchants · ${fmt(c.neither)} with neither` }] : []),
  ];
  return (
    <Card title="Merchants · who is out there and who we can reach" meta="click a number in the table to download those merchants">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(150px, 100%), 1fr))", borderTop: "1px solid #1E1E1C", borderBottom: "1px solid #D8D3C7" }}>
        {items.map((s, i) => (
          <div key={s.l} style={{ padding: "12px 12px 12px 0", paddingLeft: i ? 12 : 0, borderLeft: i ? "1px solid #E2DDD1" : undefined, display: "flex", flexDirection: "column", gap: 3 }}>
            <span className="m" style={{ fontSize: 26, letterSpacing: "-0.02em", color: s.accent ? "#C8442B" : undefined }}>{s.v}</span>
            <span style={{ fontSize: 12 }}>{s.l}</span>
            <span style={{ fontSize: 11, color: "#5E5A52" }}>{s.s}</span>
          </div>
        ))}
      </div>
      <ContactSlicer points={points} bare />
    </Card>
  );
}

const PRICE = ["〜¥1,000", "¥1,000–2,000", "¥2,000–3,000", "¥3,000–5,000", "¥5,000+", "No price info"];
const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

/** The three biggest F&B merchants with every contact detail Google has, and whether we can reach them. */
export function TopMerchants({ points }: { points: Points | null }) {
  const [by, setBy] = useState<"reviews" | "rating">("reviews");
  const top = useMemo(() => {
    if (!points) return [];
    const rows: Row[] = points.rows.map((r) => Object.fromEntries(points.cols.map((c, i) => [c, r[i]])));
    const op = rows.filter((r) => r.fnb !== "no" && r.status === "OPERATIONAL");
    const key = by === "reviews"
      ? (r: Row) => [r.reviews ?? -1, r.rating ?? 0]
      : (r: Row) => [(r.reviews ?? 0) >= 50 ? r.rating ?? 0 : -1, r.reviews ?? 0];  // rating only counts with 50+ reviews
    return op.sort((a, b) => { const [a1, a2] = key(a), [b1, b2] = key(b); return b1 - a1 || b2 - a2; }).slice(0, 3);
  }, [points, by]);

  return (
    <Card title="Top 3 merchants · full contact details" meta="operational F&B merchants">
      <div role="radiogroup" aria-label="Rank by" style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span className="lbl" style={{ color: "#5E5A52", marginRight: 4 }}>Rank by</span>
        <button role="radio" className="chip" aria-checked={by === "reviews"} aria-pressed={by === "reviews"} onClick={() => setBy("reviews")}>Most reviewed</button>
        <button role="radio" className="chip" aria-checked={by === "rating"} aria-pressed={by === "rating"} onClick={() => setBy("rating")}>Highest rated (50+ reviews)</button>
      </div>
      {!points && <span style={{ fontSize: 12, color: "#5E5A52" }}>Loading merchants…</span>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(300px, 100%), 1fr))", gap: 16 }}>
        {top.map((r, i) => {
          const reach = r.phone && r.web ? { t: "Reachable · phone + website", c: "#3F6B35" } : r.phone ? { t: "Reachable · phone only", c: "#3F6B35" }
            : r.web ? { t: "Reachable · website only", c: "#6E685C" } : { t: "Not reachable · walk-in only", c: "#A8371F" };
          const line = (label: string, v: React.ReactNode, missing = false) => (
            <div style={{ display: "grid", gridTemplateColumns: "72px 1fr", gap: 8, fontSize: 12, alignItems: "baseline" }}>
              <span className="m" style={{ fontSize: 10, color: "#8A8478" }}>{label}</span>
              <span style={{ color: missing ? "#A8371F" : undefined, wordBreak: "break-word" }}>{v}</span>
            </div>
          );
          return (
            <div key={r.maps_uri || r.name} style={{ border: "1px solid #D8D3C7", padding: 16, display: "flex", flexDirection: "column", gap: 10, background: "#FBFAF6" }}>
              <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <span className="m" style={{ display: "inline-grid", placeItems: "center", flex: "0 0 auto", width: 24, height: 24, borderRadius: "50%", background: "#1E1E1C", color: "#F8F6F0", fontSize: 12 }}>{i + 1}</span>
                <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                  <span className="jp" style={{ fontSize: 16, fontWeight: 600, lineHeight: 1.3 }}>{r.name}</span>
                  <span style={{ fontSize: 12, color: "#5E5A52" }}>{r.type_label} · {r.segment}</span>
                </div>
              </div>
              <span style={{ alignSelf: "flex-start", fontSize: 11, fontWeight: 600, color: reach.c, border: `1px solid ${reach.c}`, padding: "2px 8px" }}>{reach.t}</span>
              <div style={{ display: "flex", gap: 16, borderTop: "1px solid #E2DDD1", borderBottom: "1px solid #E2DDD1", padding: "8px 0" }}>
                <span><span className="m" style={{ fontSize: 18 }}>★{r.rating ?? "—"}</span></span>
                <span><span className="m" style={{ fontSize: 18 }}>{fmt(r.reviews)}</span> <span style={{ fontSize: 11, color: "#5E5A52" }}>reviews</span></span>
                <span style={{ fontSize: 12, color: "#5E5A52", alignSelf: "center" }}>{PRICE[r.price] ?? ""}</span>
              </div>
              {line("PHONE", r.phone ? <a className="m" href={`tel:${r.phone}`}>{r.phone}</a> : "No phone listed", !r.phone)}
              {line("WEBSITE", r.web ? <a href={r.web} target="_blank" rel="noreferrer">{host(r.web)} ↗</a> : "No website", !r.web)}
              {line("ADDRESS", <span className="jp">{r.address || "—"}</span>)}
              {line("AREA", `${r.district} · ${r.area_en}`)}
              {line("PAYMENT", PAY[r.pay] || r.pay)}
              {r.maps_uri && <a className="btn2" href={r.maps_uri} target="_blank" rel="noreferrer" style={{ alignSelf: "flex-start", textDecoration: "none", fontSize: 12 }}>Open in Google Maps ↗</a>}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
