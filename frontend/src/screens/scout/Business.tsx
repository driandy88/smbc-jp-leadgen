import { Fragment, useMemo, useState } from "react";
import type { Points } from "../../components/PlaceMap";
import { fmt, pct } from "../../lib/format";
import { isInstagram, WEB_KINDS, WEB_LABEL, webKind } from "../../lib/web";
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

type Row = Record<string, any>;
type Cls = { k: string; l: string; c: string };
const contactClass = (r: Row) => (r.phone && r.web ? "both" : r.phone ? "phone" : r.web ? "web" : "none");
/** Columns of the slicer: how a merchant can be contacted, or what its website link is. */
const VIEWS: Record<string, { l: string; of: (r: Row) => string; classes: Cls[] }> = {
  contact: {
    l: "Contact", of: contactClass,
    classes: [{ k: "both", l: "Phone + website", c: "#1E1E1C" }, { k: "phone", l: "Phone only", c: "#6E685C" },
              { k: "web", l: "Website only", c: "#A39B88" }, { k: "none", l: "No contact", c: "#C8442B" }],
  },
  web: { l: "Website type", of: webKind, classes: WEB_KINDS.map(([k, l, c]) => ({ k, l, c })) },
};
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
export function downloadCsv(rows: Row[], filename: string) {
  const head = ["name", "segment", "type", "neighbourhood", "area", "phone", "website", "website_type", "instagram", "address", "rating", "reviews", "payment", "google_maps"];
  const q = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = rows.map((r) => [r.name, r.segment, r.type_label, r.district, r.ward_en ?? r.area_en, r.phone, r.web, r.web ? WEB_LABEL[webKind(r)] : "",
    isInstagram(r.web) ? r.web : "", r.address, r.rating, r.reviews, PAY[r.pay] || r.pay, r.maps_uri].map(q).join(","));
  const blob = new Blob(["\uFEFF" + [head.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** Slice the list by contact availability against any business dimension; download any cell as a call list. */
export function ContactSlicer({ points, bare }: { points: Points | null; bare?: boolean }) {
  const [dim, setDim] = useState("segment");
  const [view, setView] = useState("contact");
  const { of: clsOf, classes: CLASSES } = VIEWS[view];
  const zero = () => Object.fromEntries([...CLASSES.map((c) => [c.k, 0]), ["n", 0]]) as Record<string, number>;
  // Reachable = phone or any website, whichever columns are shown
  const reach = (t: Record<string, number>) => (view === "contact" ? t.n - t.none : t.reach);
  const [sel, setSel] = useState<{ row: string | null; cls: string | null } | null>(null);
  const [all, setAll] = useState(false);

  const rows = useMemo<Row[]>(() => (points ? points.rows.map((r) => Object.fromEntries(points.cols.map((c, i) => [c, r[i]]))) : []), [points]);
  const d = DIMS.find((x) => x.k === dim)!;
  const base = useMemo(() => rows.filter((r) => r.fnb !== "no"), [rows]); // versions saved before F&B-only
  const table = useMemo(() => {
    const m = new Map<string, Record<string, number>>();
    for (const r of base) {
      const key = d.f(r) ?? "—";
      const t = m.get(key) || zero();
      t[clsOf(r)]++;
      t.n++;
      t.reach = (t.reach || 0) + (contactClass(r) !== "none" ? 1 : 0);
      m.set(key, t);
    }
    return [...m.entries()].sort((a, b) => b[1].n - a[1].n);
  }, [base, d, view]);
  const totals = useMemo(() => {
    const t = zero();
    for (const r of base) { t[clsOf(r)]++; t.n++; t.reach = (t.reach || 0) + (contactClass(r) !== "none" ? 1 : 0); }
    return t;
  }, [base, view]);

  const Wrap = bare ? Bare : Card;
  if (!points) return <Wrap title="Contact slicer"><span style={{ fontSize: 12, color: "#5E5A52" }}>Loading merchants…</span></Wrap>;
  const picked = sel ? base.filter((r) => (sel.row == null || d.f(r) === sel.row) && (sel.cls == null || clsOf(r) === sel.cls)) : [];
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
        <span className="lbl" style={{ color: "#5E5A52", marginLeft: "auto" }}>Columns</span>
        <div role="radiogroup" aria-label="Columns" className="seg">
          {Object.entries(VIEWS).map(([k, v]) => <button key={k} role="radio" aria-checked={view === k} onClick={() => { setView(k); setSel(null); }}>{v.l}</button>)}
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: view === "contact" ? 760 : 940 }}>
          <div className={`m slice-grid${view === "web" ? " slice-grid-web" : ""}`} style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>{d.l.toUpperCase()}</span><span>F&B MERCHANTS</span>
            {CLASSES.map((c) => <span key={c.k} style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><span style={{ width: 8, height: 8, background: c.c }} />{c.l.toUpperCase()}</span>)}
            <span>REACHABLE</span><span>MIX</span>
          </div>
          {[["All", totals] as [string, Record<string, number>], ...shown].map(([key, t], i) => {
            const row = i === 0 ? null : key;
            return (
              <div key={key + i} className={`slice-grid${view === "web" ? " slice-grid-web" : ""}`} style={{ fontSize: 12, padding: "3px 0", borderBottom: i === 0 ? "1px solid #1E1E1C" : "1px solid #E2DDD1", alignItems: "center", fontWeight: i === 0 ? 600 : 400 }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={key}>{key}</span>
                {cell(row, null, t.n, 0)}
                {CLASSES.map((c) => <Fragment key={c.k}>{cell(row, c.k, t[c.k], t.n, c.k === "none" && t[c.k] ? "#A8371F" : undefined)}</Fragment>)}
                <span className="m" style={{ color: (100 * reach(t)) / Math.max(1, t.n) < 80 ? "#A8371F" : undefined }}>{pct((100 * reach(t)) / Math.max(1, t.n), 0)}</span>
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
          <span style={{ fontSize: 12, color: "#5E5A52" }}>Select a number in the table, e.g. <b>Izakaya & bars × Phone only</b>, to get that call list with names, phone, website type, Instagram, address and Google Maps link. <b>Website type</b> splits the links into the merchant's own site, a group / chain site, social media, booking sites and gourmet portals.</span>
        )}
      </div>
    </Wrap>
  );
}

/** Per area picked in step 1: its three biggest F&B segments as bars, split into reachable and not. */
export function AreaView({ p, points }: { p: Profile; points: Points | null }) {
  const areas = useMemo(() => {
    if (!points) return [];
    const picked = (p.areas || []).filter((a: any) => (a.selected ?? a.code !== "outside") && a.per_km2 != null);
    const groups = new Map<string, Row[]>();
    for (const r of points.rows.map((row) => Object.fromEntries(points.cols.map((c, i) => [c, row[i]])) as Row)) {
      const k: string = r.ward_en ?? r.area_en;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(r);
    }
    return picked.map((a: any) => {
      const rows = groups.get(a.en) || [];
      const segs = new Map<string, { n: number; reach: number }>();
      for (const r of rows) {
        const t = segs.get(r.segment) || { n: 0, reach: 0 };
        t.n++;
        if (contactClass(r) !== "none") t.reach++;
        segs.set(r.segment, t);
      }
      return { name: a.en, density: a.per_km2 as number, n: rows.length,
               top: [...segs.entries()].sort((x, y) => y[1].n - x[1].n).slice(0, 3) };
    }).sort((x: any, y: any) => y.density - x.density);
  }, [points, p]);

  if (!points) return <Card title="Areas"><span style={{ fontSize: 12, color: "#5E5A52" }}>Loading merchants…</span></Card>;
  if (!areas.length) return null;
  const max = Math.max(1, ...areas.flatMap((a: any) => a.top.map(([, t]: [string, { n: number }]) => t.n)));
  return (
    <Card title="Areas · top 3 F&B segments in each area you picked" meta="bar = merchants · same scale across areas">
      <div style={{ display: "flex", gap: 16, fontSize: 11, color: "#5E5A52" }}>
        <span className="legend"><span style={{ background: "#1E1E1C" }} />Reachable (phone or website)</span>
        <span className="legend"><span style={{ background: "#C8442B" }} />Not reachable</span>
      </div>
      <div className="top3-grid">
        {areas.map((a: any) => (
          <div key={a.name} style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, borderBottom: "1px solid #1E1E1C", paddingBottom: 6 }}>
              <span className="serif" style={{ fontSize: 22 }}>{a.name}</span>
              <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{fmt(a.n)} merchants · {fmt(Math.round(a.density))}/km²</span>
            </div>
            {a.top.map(([seg, t]: [string, { n: number; reach: number }], i: number) => (
              <div key={seg} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13 }}>
                  <span><span className="m" style={{ color: "#8A8478", marginRight: 6 }}>{i + 1}</span>{seg}</span>
                  <span className="m">{fmt(t.n)}</span>
                </span>
                <span className="top3-bar" title={`${seg} in ${a.name}: ${t.reach} reachable, ${t.n - t.reach} not`} style={{ width: `${(100 * t.n) / max}%` }}>
                  <span style={{ flex: t.reach, background: "#1E1E1C" }} />
                  {t.n > t.reach && <span style={{ flex: t.n - t.reach, background: "#C8442B" }} />}
                </span>
                <span style={{ fontSize: 11, color: "#5E5A52" }}>
                  {fmt(t.reach)} reachable ({pct((100 * t.reach) / t.n, 0)}) · {fmt(t.n - t.reach)} not
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </Card>
  );
}
