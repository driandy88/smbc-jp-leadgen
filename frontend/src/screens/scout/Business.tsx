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
/** Save merchants as a CSV call list (BOM so Excel reads the Japanese names). */
function downloadCsv(rows: Row[], filename: string) {
  const head = ["name", "segment", "type", "neighbourhood", "ward", "phone", "website", "address", "rating", "reviews", "payment", "google_maps"];
  const q = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = rows.map((r) => [r.name, r.segment, r.type_label, r.district, r.area_en, r.phone, r.web, r.address, r.rating, r.reviews, PAY[r.pay] || r.pay, r.maps_uri].map(q).join(","));
  const blob = new Blob(["\uFEFF" + [head.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

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

  const download = () => downloadCsv(picked, `merchants_${(sel?.row || "all").replace(/\W+/g, "-")}_${sel?.cls || "any"}.csv`);
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
  const indie = p.rows - (p.areas || []).reduce((n: number, a: { chains?: number }) => n + (a.chains || 0), 0);
  const items = [
    { v: fmt(p.rows), l: "unique merchants", s: `${fmt(p.areas?.length)} areas · ${fmt(p.overview?.types)} types` },
    { v: fmt(f.core.n), l: "F&B", s: pct(f.core.pct), accent: true },
    ...(c ? [{ v: pct(p.overview.cash_or_unknown_pct, 0), l: "cash-only or no card info", s: `${fmt(c.cash_callable.n)} of ${fmt(c.cash_callable.of)} list a phone` }] : []),
    { v: pct(indie / p.rows * 100, 0), l: "independent (not a chain)", s: `${fmt(p.rows - indie)} chain branches` },
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

const BY = [
  { k: "segment", l: "F&B segment", f: (r: Row) => r.segment },
  { k: "type", l: "Place type", f: (r: Row) => r.type_label },
] as const;

/** The three categories with the most merchants we can reach, and how many in each we cannot. */
export function TopCategories({ points }: { points: Points | null }) {
  const [by, setBy] = useState<"segment" | "type">("segment");
  const top = useMemo(() => {
    if (!points) return [];
    const f = BY.find((x) => x.k === by)!.f;
    const groups = new Map<string, Row[]>();
    for (const r of points.rows.map((row) => Object.fromEntries(points.cols.map((c, i) => [c, row[i]])))) {
      if (r.fnb === "no") continue;
      const k = f(r) ?? "—";
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(r);
    }
    return [...groups.entries()]
      .map(([name, rows]) => {
        const n: Record<string, number> = { both: 0, phone: 0, web: 0, none: 0 };
        const types = new Map<string, number>();
        for (const r of rows) {
          n[contactClass(r)]++;
          types.set(r.type_label, (types.get(r.type_label) || 0) + 1);
        }
        return { name, rows, n, reach: rows.length - n.none, cash: rows.filter((r) => r.pay === "cash" || r.pay === "none").length,
                 types: [...types.entries()].sort((x, y) => y[1] - x[1]).slice(0, 3) };
      })
      .sort((x, y) => y.reach - x.reach)
      .slice(0, 3);
  }, [points, by]);

  return (
    <Card title="Top 3 categories · most merchants we can reach" meta="F&B merchants · reachable = phone or website">
      <div role="radiogroup" aria-label="Category" style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span className="lbl" style={{ color: "#5E5A52", marginRight: 4 }}>Category</span>
        {BY.map((x) => <button key={x.k} role="radio" className="chip" aria-checked={by === x.k} aria-pressed={by === x.k} onClick={() => setBy(x.k)}>{x.l}</button>)}
      </div>
      {!points && <span style={{ fontSize: 12, color: "#5E5A52" }}>Loading merchants…</span>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(300px, 100%), 1fr))", gap: 16 }}>
        {top.map((t, i) => {
          const total = t.rows.length;
          const share = (v: number) => (100 * v) / Math.max(1, total);
          const file = t.name.replace(/\W+/g, "-");
          return (
            <div key={t.name} style={{ border: "1px solid #D8D3C7", padding: 16, display: "flex", flexDirection: "column", gap: 12, background: "#FBFAF6" }}>
              <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <span className="m" style={{ display: "inline-grid", placeItems: "center", flex: "0 0 auto", width: 24, height: 24, borderRadius: "50%", background: "#1E1E1C", color: "#F8F6F0", fontSize: 12 }}>{i + 1}</span>
                <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                  <span style={{ fontSize: 16, fontWeight: 600, lineHeight: 1.3 }}>{t.name}</span>
                  <span style={{ fontSize: 12, color: "#5E5A52" }}>{fmt(total)} merchants{by === "segment" ? ` · ${t.types.map(([k, v]) => `${k} ${fmt(v)}`).join(" · ")}` : ""}</span>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", borderTop: "1px solid #E2DDD1", borderBottom: "1px solid #E2DDD1" }}>
                <div style={{ padding: "10px 0", display: "flex", flexDirection: "column", gap: 2 }}>
                  <span className="m" style={{ fontSize: 26, color: "#3F6B35" }}>{fmt(t.reach)}</span>
                  <span style={{ fontSize: 12 }}>reachable <span className="m" style={{ color: "#5E5A52" }}>{pct(share(t.reach), 0)}</span></span>
                </div>
                <div style={{ padding: "10px 0 10px 12px", borderLeft: "1px solid #E2DDD1", display: "flex", flexDirection: "column", gap: 2 }}>
                  <span className="m" style={{ fontSize: 26, color: "#A8371F" }}>{fmt(t.n.none)}</span>
                  <span style={{ fontSize: 12 }}>not reachable <span className="m" style={{ color: "#5E5A52" }}>{pct(share(t.n.none), 0)}</span></span>
                </div>
              </div>

              <div style={{ display: "flex", height: 10, gap: 1 }}>
                {CLASSES.map((c) => <span key={c.k} title={`${c.l} · ${t.n[c.k]}`} style={{ width: `${share(t.n[c.k])}%`, background: c.c, minWidth: t.n[c.k] ? 2 : 0 }} />)}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {CLASSES.map((c) => (
                  <div key={c.k} style={{ display: "grid", gridTemplateColumns: "12px 1fr 52px 40px", gap: 8, alignItems: "center", fontSize: 12 }}>
                    <span style={{ width: 9, height: 9, background: c.c }} /><span>{c.l}</span>
                    <span className="m" style={{ textAlign: "right" }}>{fmt(t.n[c.k])}</span>
                    <span className="m" style={{ textAlign: "right", color: "#8A8478", fontSize: 11 }}>{pct(share(t.n[c.k]), 0)}</span>
                  </div>
                ))}
              </div>
              <span style={{ fontSize: 12, color: "#5E5A52" }}>{pct(share(t.cash), 0)} cash-only or no card info</span>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button className="btn2" style={{ fontSize: 12 }} disabled={!t.reach} onClick={() => downloadCsv(t.rows.filter((r) => contactClass(r) !== "none"), `${file}_reachable.csv`)}>Download reachable</button>
                <button className="btn2" style={{ fontSize: 12 }} disabled={!t.n.none} onClick={() => downloadCsv(t.rows.filter((r) => contactClass(r) === "none"), `${file}_not-reachable.csv`)}>Download not reachable</button>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
