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
  { k: "ward", l: "Area", f: (r) => r.ward_en ?? r.area_en },
  { k: "pay", l: "Payment", f: (r) => PAY[r.pay] || r.pay },
  { k: "rating", l: "Rating", f: rating },
  { k: "type", l: "Place type", f: (r) => r.type_label },
];
/** Save merchants as a CSV call list (BOM so Excel reads the Japanese names). */
function downloadCsv(rows: Row[], filename: string) {
  const head = ["name", "segment", "type", "neighbourhood", "area", "phone", "website", "address", "rating", "reviews", "payment", "google_maps"];
  const q = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = rows.map((r) => [r.name, r.segment, r.type_label, r.district, r.ward_en ?? r.area_en, r.phone, r.web, r.address, r.rating, r.reviews, PAY[r.pay] || r.pay, r.maps_uri].map(q).join(","));
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
  const [sel, setSel] = useState<{ row: string | null; cls: string | null } | null>(null);
  const [all, setAll] = useState(false);

  const rows = useMemo<Row[]>(() => (points ? points.rows.map((r) => Object.fromEntries(points.cols.map((c, i) => [c, r[i]]))) : []), [points]);
  const d = DIMS.find((x) => x.k === dim)!;
  const base = useMemo(() => rows.filter((r) => r.fnb !== "no"), [rows]); // versions saved before F&B-only
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
      </div>

      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 760 }}>
          <div className="m slice-grid" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>{d.l.toUpperCase()}</span><span>F&B MERCHANTS</span>
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
            <span style={{ fontSize: 13 }}><b className="m">{fmt(picked.length)}</b> F&B merchants · {selLabel}</span>
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
    { v: fmt(p.rows), l: "F&B merchants", s: `${fmt((p.areas || []).filter((a: any) => a.selected !== false).length)} areas · incl. ${fmt(f.related?.n)} F&B-related venues`, accent: true },
    ...(c ? [{ v: pct(p.overview.cash_or_unknown_pct, 0), l: "cash-only or no card info", s: `${fmt(c.cash_callable.n)} of ${fmt(c.cash_callable.of)} list a phone` }] : []),
    { v: pct(indie / p.rows * 100, 0), l: "independent (not a chain)", s: `${fmt(p.rows - indie)} chain branches` },
    ...(c ? [{ v: pct(c.either_pct, 0), l: "reachable by phone or web", s: `${fmt(c.either)} merchants · ${fmt(c.neither)} with neither` }] : []),
  ];
  return (
    <Card title="F&B merchants · who is out there and who we can reach" meta="click a number in the table to download those merchants">
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

type Seg = { name: string; rows: Row[]; n: Record<string, number>; reach: number; cash: number };
const isCash = (r: Row) => r.pay === "cash" || r.pay === "none";

/** Per area: how dense F&B is, how reachable, and the three biggest F&B segments split by reachable or not. */
export function AreaView({ p, points }: { p: Profile; points: Points | null }) {
  const areas = useMemo(() => {
    if (!points) return [];
    const byName = new Map<string, any>((p.areas || []).map((a: any) => [a.en, a]));
    const groups = new Map<string, Row[]>();
    for (const r of points.rows.map((row) => Object.fromEntries(points.cols.map((c, i) => [c, row[i]])) as Row)) {
      if (r.fnb === "no") continue;
      const k: string = r.ward_en ?? r.area_en;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(r);
    }
    return [...groups.entries()].map(([name, rows]) => {
      const meta = byName.get(name);
      const segs = new Map<string, Row[]>();
      for (const r of rows) {
        if (!segs.has(r.segment)) segs.set(r.segment, []);
        segs.get(r.segment)!.push(r);
      }
      const top: Seg[] = [...segs.entries()].map(([sn, sr]) => {
        const n: Record<string, number> = { both: 0, phone: 0, web: 0, none: 0 };
        for (const r of sr) n[contactClass(r)]++;
        return { name: sn, rows: sr, n, reach: sr.length - n.none, cash: sr.filter(isCash).length };
      }).sort((x, y) => y.rows.length - x.rows.length).slice(0, 3);
      const districts = new Map<string, number>();
      for (const r of rows) if (!String(r.district).endsWith("· other")) districts.set(r.district, (districts.get(r.district) || 0) + 1);
      const hub = [...districts.entries()].sort((x, y) => y[1] - x[1])[0];
      return { name, rows, top, hub, selected: meta?.selected ?? name !== "Outside", density: meta?.per_km2 ?? null,
               km2: meta?.km2 ?? null, reach: rows.filter((r) => contactClass(r) !== "none").length, cash: rows.filter(isCash).length };
    }).sort((x, y) => Number(y.selected) - Number(x.selected) || (y.density ?? 0) - (x.density ?? 0) || y.rows.length - x.rows.length);
  }, [points, p]);

  // Partly covered wards with a sliver of the list go on one line instead of a row each
  const total = areas.reduce((n, a) => n + a.rows.length, 0);
  const shown = areas.filter((a) => a.selected || a.rows.length >= 0.05 * total);
  const folded = areas.filter((a) => !shown.includes(a));
  const maxD = Math.max(1, ...areas.map((a) => a.density ?? 0));
  if (!points) return <Card title="Areas"><span style={{ fontSize: 12, color: "#5E5A52" }}>Loading merchants…</span></Card>;
  return (
    <Card title="Areas · density and the top 3 F&B segments in each" meta="ranked by F&B merchants per km² · reachable = phone or website">
      {shown.map((a, i) => {
        const share = (v: number) => pct((100 * v) / Math.max(1, a.rows.length), 0);
        return (
          <div key={a.name} className="area-row">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                <span className="m" style={{ fontSize: 11, color: "#C8442B" }}>{String(i + 1).padStart(2, "0")}</span>
                <span className="serif" style={{ fontSize: 24, lineHeight: 1.1 }}>{a.name}</span>
              </div>
              {a.selected && a.density != null ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span><span className="m" style={{ fontSize: 26, color: "#C8442B" }}>{fmt(Math.round(a.density))}</span> <span style={{ fontSize: 12 }}>F&B / km²</span></span>
                  <Bar v={a.density} max={maxD} c="#C8442B" />
                </div>
              ) : <span style={{ fontSize: 12, color: "#8A8478", lineHeight: 1.5 }}>Partly covered: only the edge next to your selected areas was searched, so no density.</span>}
              <div className="m" style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "2px 10px", fontSize: 12 }}>
                <span>{fmt(a.rows.length)}</span><span style={{ color: "#5E5A52" }}>F&B merchants{a.km2 ? ` · ${a.km2} km²` : ""}</span>
                <span>{share(a.reach)}</span><span style={{ color: "#5E5A52" }}>reachable</span>
                <span>{share(a.cash)}</span><span style={{ color: "#5E5A52" }}>cash-only or no card info</span>
              </div>
              {a.hub && <span style={{ fontSize: 12, color: "#5E5A52" }}>Busiest neighbourhood: <b style={{ color: "#1E1E1C" }}>{a.hub[0]}</b> ({fmt(a.hub[1])})</span>}
            </div>
            <div className="area-segs">
              {a.top.map((t, j) => {
                const tot = t.rows.length;
                const w = (v: number) => `${(100 * v) / Math.max(1, tot)}%`;
                const file = `${a.name}_${t.name}`.replace(/\W+/g, "-");
                return (
                  <div key={t.name} style={{ border: "1px solid #D8D3C7", background: "#FBFAF6", padding: 12, display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
                    <span style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                      <span className="m" style={{ fontSize: 11, color: "#8A8478" }}>{j + 1}</span>
                      <span style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>{t.name}</span>
                    </span>
                    <span className="m" style={{ fontSize: 12, color: "#5E5A52" }}>{fmt(tot)} merchants · {share(tot)} of area</span>
                    <div style={{ display: "flex", height: 8, gap: 1 }}>
                      {CLASSES.map((c) => <span key={c.k} title={`${c.l} · ${t.n[c.k]}`} style={{ width: w(t.n[c.k]), background: c.c, minWidth: t.n[c.k] ? 2 : 0 }} />)}
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", fontSize: 12 }}>
                      <span><b className="m" style={{ color: "#3F6B35", fontSize: 16 }}>{fmt(t.reach)}</b> reachable</span>
                      <span><b className="m" style={{ color: "#A8371F", fontSize: 16 }}>{fmt(t.n.none)}</b> not reachable</span>
                    </div>
                    <span style={{ fontSize: 11, color: "#5E5A52" }}>{pct((100 * t.cash) / Math.max(1, tot), 0)} cash-only or no card info</span>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <button className="btn2" style={{ fontSize: 11, padding: "4px 8px" }} disabled={!t.reach} onClick={() => downloadCsv(t.rows.filter((r) => contactClass(r) !== "none"), `${file}_reachable.csv`)}>↓ Reachable</button>
                      <button className="btn2" style={{ fontSize: 11, padding: "4px 8px" }} disabled={!t.n.none} onClick={() => downloadCsv(t.rows.filter((r) => contactClass(r) === "none"), `${file}_not-reachable.csv`)}>↓ Not reachable</button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
      {!!folded.length && (
        <span style={{ fontSize: 12, color: "#5E5A52", lineHeight: 1.6, borderTop: "1px solid #E2DDD1", paddingTop: 10 }}>
          Also found along the edges of your areas ({fmt(folded.reduce((n, a) => n + a.rows.length, 0))} merchants, partly covered):{" "}
          {folded.map((a) => `${a.name} ${fmt(a.rows.length)}`).join(" · ")}
        </span>
      )}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11, color: "#5E5A52" }}>
        {CLASSES.map((c) => <span key={c.k} className="legend"><span style={{ background: c.c }} />{c.l}</span>)}
        <span>Density = F&B merchants ÷ the area's land size.</span>
      </div>
    </Card>
  );
}
