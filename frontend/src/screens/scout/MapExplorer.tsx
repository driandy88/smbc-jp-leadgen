import { getHexagonAreaAvg, latLngToCell } from "h3-js";
import { useEffect, useMemo, useState } from "react";
import type { Outline } from "../../components/HexMap";
import { HexShade, PlaceMap, Points } from "../../components/PlaceMap";
import { fmt, pct } from "../../lib/format";
import { WEB_KINDS, WEB_LABEL, webKind } from "../../lib/web";
import { downloadCsv } from "./Business";
import { Profile } from "./types";

type Row = Record<string, any>;
/** What the explorer shows; the Websites card sets it too. */
export type ExplorerView = { area: string; web: string; reset?: number };
type Layer = "off" | "density" | "top20" | "top10";

const RES = 9; // the backend's AREA_HEX_RES
const HEX_KM2 = getHexagonAreaAvg(RES, "km2");
// F&B merchants per km² in a hex, densest first
// Heat scale, least to most packed
const RAMP = ["#FBE7B5", "#F5B86A", "#E8803F", "#C8442B", "#8F1F14", "#4A0E08"];
const hexToRgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
/** Colour for t in 0..1 along the ramp. */
const heat = (t: number) => {
  const x = Math.min(1, Math.max(0, t)) * (RAMP.length - 1), i = Math.min(RAMP.length - 2, Math.floor(x)), f = x - i;
  const [a, b] = [hexToRgb(RAMP[i]), hexToRgb(RAMP[i + 1])];
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",")})`;
};
// Log scale between the quietest and the busiest hex shown: one outlier block doesn't wash out the rest
const scale = (lo: number, hi: number) => (n: number) => (hi > lo ? (Math.log(n) - Math.log(lo)) / (Math.log(hi) - Math.log(lo)) : 1);
const PAY: Record<string, string> = { cash: "Cash only", none: "No payment info", card: "Card", nfc: "Card + NFC / IC" };
const majority = (xs: string[]) => [...xs.reduce((m, x) => m.set(x, (m.get(x) || 0) + 1), new Map<string, number>())].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—";

/** One place to explore the list: pick an area and a website type, shade hexes by density, click a hex to see it up close. */
export function MapExplorer({ p, points, outline, view, setView }: { p: Profile; points: Points | null; outline: Outline | null; view: ExplorerView; setView: (v: ExplorerView) => void }) {
  const [layer, setLayer] = useState<Layer>("density");
  const [hex, setHex] = useState<string | null>(null);
  useEffect(() => setHex(null), [view.area, view.reset]); // a new area, or a pick from the Websites card

  const picked: Row[] = useMemo(() => (p.areas || []).filter((a: Row) => a.selected ?? a.code !== "outside"), [p]);
  const pickedNames = useMemo(() => new Set(picked.map((a) => a.en)), [picked]);
  const rows = useMemo<Row[]>(() => (points ? points.rows.map((r) => {
    const o = Object.fromEntries(points.cols.map((c, i) => [c, r[i]])) as Row;
    o.cell = o.lat != null ? latLngToCell(o.lat, o.lng, RES) : null;
    o.area = o.ward_en ?? o.area_en;
    return o;
  }) : []).filter((r) => r.fnb !== "no"), [points]);

  // Merchants per hex and area, counted like the analysis (a hex on a ward border counts in each ward for
  // that ward's merchants); one shared cutoff for the top 20% / 10% (from the analysis when it has one)
  const cells = useMemo(() => {
    const m = new Map<string, Row[]>();
    for (const r of rows) if (r.cell && pickedNames.has(r.area)) m.set(`${r.area}|${r.cell}`, [...(m.get(`${r.area}|${r.cell}`) || []), r]);
    return [...m].map(([k, rs]) => ({ k, h: rs[0].cell as string, n: rs.length, area: rs[0].area as string, district: majority(rs.map((r) => r.district).filter(Boolean)) }))
      .sort((a, b) => b.n - a.n);
  }, [rows, pickedNames]);
  const cut = useMemo(() => {
    const hot = picked.find((a) => a.hex?.hot)?.hex.hot;
    if (hot) return { top20: hot[0].min as number, top10: hot[1].min as number, pool: hot[0].pool as number };
    const ns = cells.map((c) => c.n).sort((a, b) => a - b);
    const q = (x: number) => ns[Math.min(ns.length - 1, Math.floor(x * ns.length))] ?? 0;
    return { top20: q(0.8), top10: q(0.9), pool: ns.length };
  }, [picked, cells]);

  const inArea = (r: Row) => view.area === "all" || r.area === view.area;
  const areaRows = useMemo(() => rows.filter(inArea), [rows, view.area]);
  const scopeRows = hex ? areaRows.filter((r) => r.cell === hex) : areaRows; // what the panel and table describe
  const shownRows = view.web === "all" ? scopeRows : scopeRows.filter((r) => webKind(r) === view.web);
  const mapPoints = useMemo<Points | null>(() => points && {
    cols: points.cols,
    rows: (view.web === "all" ? areaRows : areaRows.filter((r) => webKind(r) === view.web)).map((o) => points.cols.map((c) => o[c])),
  }, [points, areaRows, view.web]);

  const areaCells = cells.filter((c) => view.area === "all" || c.area === view.area);
  const hotCells = layer === "top10" ? areaCells.filter((c) => c.n >= cut.top10) : layer === "top20" ? areaCells.filter((c) => c.n >= cut.top20) : [];
  const shown = layer === "density" ? areaCells : hotCells;
  const range = { lo: Math.min(...shown.map((c) => c.n)), hi: Math.max(...shown.map((c) => c.n)) };
  const shades = useMemo<HexShade[]>(() => {
    const tip = (c: { n: number; district: string }) => `${c.district} · ${fmt(c.n)} merchants · ${fmt(Math.round(c.n / HEX_KM2))}/km²`;
    // One polygon per hex: a border hex shows its busiest ward's count
    const once = (cs: typeof cells) => cs.filter((c, i) => cs.findIndex((d) => d.h === c.h) === i);
    const t = scale(range.lo, range.hi);
    return once(shown).map((c) => ({ h: c.h, color: heat(t(c.n)), tip: tip(c), opacity: 0.72 }));
  }, [layer, view.area, cells, cut]);

  const pick = (v: Partial<ExplorerView>) => { setHex(null); setView({ ...view, ...v }); };
  const area = picked.find((a) => a.en === view.area);
  const curCell = hex ? cells.find((c) => c.h === hex && (view.area === "all" || c.area === view.area)) : null;

  if (!points) return <span style={{ fontSize: 12, color: "#5E5A52" }}>Loading merchants…</span>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Filters */}
      <div className="ex-filters">
        <Chips label="Area" value={view.area} onChange={(area) => pick({ area })}
          opts={[{ k: "all", l: "All areas", n: rows.length }, ...picked.map((a) => ({ k: a.en, l: a.en, n: rows.filter((r) => r.area === a.en).length }))]} />
        <Chips label="Website" value={view.web} onChange={(web) => setView({ ...view, web })}
          opts={[{ k: "all", l: "Any" }, ...WEB_KINDS.map(([k, l, c]) => ({ k, l, c, n: scopeRows.filter((r) => webKind(r) === k).length }))]} />
        <Chips label="Hexes" value={layer} onChange={(l) => { setLayer(l as Layer); setHex(null); }}
          opts={[{ k: "off", l: "Off" }, { k: "density", l: "Density" }, { k: "top20", l: "Top 20%" }, { k: "top10", l: "Top 10%" }]} />
      </div>

      <div className="ex-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
          <PlaceMap points={mapPoints} outline={outline} hotspots={layer === "off" ? p.hotspots : undefined} highlight={hex} hexes={hex ? undefined : shades} dim={!hex && layer !== "off"}
            onHex={setHex} fitKey={view.area} height={600} />
          <HexLegend layer={layer} cut={cut} range={range} />
        </div>

        {/* Side panel: the picked area or hex */}
        <div className="ex-panel">
          {curCell ? (
            <HexCard c={curCell} rows={scopeRows} cut={cut} onBack={() => setHex(null)} />
          ) : (
            <AreaCard name={area?.en ?? "All picked areas"} n={areaRows.length} perKm2={area?.per_km2} h={area?.hex ?? sumHex(picked, cells)} cut={cut} />
          )}

          <Block t={`Website · ${curCell ? "this hex" : area?.en ?? "all areas"}`} meta="click to filter">
            <WebBars rows={scopeRows} active={view.web} onPick={(k) => setView({ ...view, web: view.web === k ? "all" : k })} />
          </Block>

          {!curCell && hotCells.length > 0 && (
            <Block t={`${layer === "top10" ? "Top 10%" : "Top 20%"} hexes · ${fmt(hotCells.length)}`} meta="click to zoom">
              <div style={{ maxHeight: 240, overflow: "auto", display: "flex", flexDirection: "column" }}>
                {hotCells.map((c, i) => (
                  <button key={c.k} className="ex-row" onClick={() => setHex(c.h)}>
                    <span className="m" style={{ color: "#8A8478", width: 22 }}>{i + 1}</span>
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.district}</span>
                    <span className="m">{fmt(c.n)}</span>
                    <span className="m" style={{ color: "#5E5A52", width: 74, textAlign: "right" }}>{fmt(Math.round(c.n / HEX_KM2))}/km²</span>
                  </button>
                ))}
              </div>
            </Block>
          )}

          <button className="btn2" style={{ alignSelf: "flex-start" }} disabled={!shownRows.length}
            onClick={() => downloadCsv(shownRows, `merchants_${curCell ? curCell.district : view.area}_${view.web}.csv`.replace(/[^\w.-]+/g, "-"))}>
            Download {fmt(shownRows.length)} merchants (CSV)
          </button>
        </div>
      </div>

      {curCell && <HexMerchants rows={shownRows} />}
    </div>
  );
}

function Chips({ label, value, opts, onChange }: { label: string; value: string; opts: { k: string; l: string; n?: number; c?: string }[]; onChange: (k: string) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <span className="lbl" style={{ color: "#5E5A52", width: 64 }}>{label}</span>
      <div role="radiogroup" aria-label={label} style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {opts.map((o) => (
          <button key={o.k} role="radio" className="chip" aria-checked={value === o.k} aria-pressed={value === o.k} onClick={() => onChange(o.k)}>
            {o.c && <span style={{ width: 8, height: 8, background: o.c, display: "inline-block", marginRight: 6 }} />}
            {o.l}{o.n != null && <span className="m" style={{ marginLeft: 6, opacity: 0.6, fontSize: 11 }}>{fmt(o.n)}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

const Block = ({ t, meta, children }: { t: string; meta?: string; children: React.ReactNode }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid #1E1E1C", paddingTop: 8 }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
      <span className="lbl">{t}</span>{meta && <span style={{ fontSize: 11, color: "#8A8478" }}>{meta}</span>}
    </div>
    {children}
  </div>
);

const Stat = ({ v, l }: { v: string; l: string }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
    <span className="m" style={{ fontSize: 20, letterSpacing: "-0.02em" }}>{v}</span>
    <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.3 }}>{l}</span>
  </div>
);

type Cut = { top20: number; top10: number; pool: number };
type HexStats = { hexes: number; active: number; cover?: Record<string, number>; hot?: { hexes: number; share: number }[]; max: number };

/** Totals over every picked area, for "All areas". */
function sumHex(picked: Row[], cells: { n: number }[]): HexStats | null {
  const hs = picked.map((a) => a.hex).filter(Boolean);
  if (!hs.length) return null;
  const tot = cells.reduce((s, c) => s + c.n, 0);
  // Fewest hexes (busiest first) that hold that share of the merchants
  const need = (q: number) => { let acc = 0; return cells.findIndex((c) => (acc += c.n) >= q * tot) + 1; };
  const cover = { "50": need(0.5), "80": need(0.8), "90": need(0.9) };
  const hot = hs[0].hot ? [0, 1].map((i) => {
    const n = hs.reduce((s: number, h: Row) => s + h.hot[i].hexes, 0);
    const held = hs.reduce((s: number, h: Row) => s + h.hot[i].cells.reduce((t: number, c: Row) => t + c.n, 0), 0);
    return { hexes: n, share: (100 * held) / Math.max(1, tot) };
  }) : undefined;
  return { hexes: hs.reduce((s: number, h: Row) => s + h.hexes, 0), active: hs.reduce((s: number, h: Row) => s + h.active, 0), cover, hot, max: cells[0]?.n ?? 0 };
}

function AreaCard({ name, n, perKm2, h, cut }: { name: string; n: number; perKm2?: number; h: HexStats | null; cut: Cut }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
        <span className="serif" style={{ fontSize: 24 }}>{name}</span>
        <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{fmt(n)} merchants{perKm2 ? ` · ${fmt(Math.round(perKm2))}/km²` : ""}</span>
      </div>
      {h ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 14px" }}>
            <Stat v={h.cover ? fmt(h.cover["50"]) : "—"} l={`hexes hold half the merchants (of ${fmt(h.active)} with F&B)`} />
            <Stat v={h.cover ? `${fmt(h.cover["80"])} / ${fmt(h.cover["90"])}` : "—"} l="hexes hold 80% / 90%" />
            <Stat v={h.hot ? fmt(h.hot[0].hexes) : "—"} l={`top-20% hexes (${fmt(cut.top20)}+ each)${h.hot ? ` · hold ${pct(h.hot[0].share, 0)}` : ""}`} />
            <Stat v={h.hot ? fmt(h.hot[1].hexes) : "—"} l={`top-10% hexes (${fmt(cut.top10)}+ each)${h.hot ? ` · hold ${pct(h.hot[1].share, 0)}` : ""}`} />
          </div>
          <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.45 }}>
            A hex is a ~350 m block (≈{HEX_KM2.toFixed(2)} km²). Busiest here: {fmt(h.max)} merchants. Fewer hexes holding half the merchants = a tighter cluster a rep can walk.
          </span>
        </>
      ) : <span style={{ fontSize: 11, color: "#5E5A52" }}>Re-run Analyze to get hex density for this version.</span>}
    </div>
  );
}

function HexCard({ c, rows, cut, onBack }: { c: { h: string; n: number; district: string; area: string }; rows: Row[]; cut: Cut; onBack: () => void }) {
  const reach = rows.filter((r) => r.phone || r.web).length;
  const cash = rows.filter((r) => r.pay === "cash" || r.pay === "none").length;
  const tier = c.n >= cut.top10 ? "Top 10% hex" : c.n >= cut.top20 ? "Top 20% hex" : "Hex";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <button className="btn2" onClick={onBack} style={{ alignSelf: "flex-start", minHeight: 0, padding: "4px 10px", fontSize: 12 }}>← Back to {c.area}</button>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
        <span className="serif" style={{ fontSize: 24 }}>{c.district}</span>
        <span className="m" style={{ fontSize: 11, color: "#C8442B" }}>{tier}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 14px" }}>
        <Stat v={fmt(c.n)} l="F&B merchants in this block" />
        <Stat v={fmt(Math.round(c.n / HEX_KM2))} l="per km²" />
        <Stat v={pct((100 * reach) / Math.max(1, rows.length), 0)} l="reachable by phone or web" />
        <Stat v={pct((100 * cash) / Math.max(1, rows.length), 0)} l="cash-only or no card info" />
      </div>
    </div>
  );
}

/** Website type of the merchants in scope, as clickable bars. */
function WebBars({ rows, active, onPick }: { rows: Row[]; active: string; onPick: (k: string) => void }) {
  const n = Math.max(1, rows.length);
  const insta = rows.filter((r) => r.web && /instagram\.com/i.test(r.web)).length;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {WEB_KINDS.map(([k, l, c]) => {
        const v = rows.filter((r) => webKind(r) === k).length;
        return (
          <button key={k} className="ex-row" aria-pressed={active === k} onClick={() => onPick(k)} style={{ opacity: active !== "all" && active !== k ? 0.45 : 1 }}>
            <span style={{ width: 118, textAlign: "left" }}>{l}</span>
            <span style={{ flex: 1, height: 8, background: "#E2DDD1" }}><span style={{ display: "block", height: 8, width: `${(100 * v) / n}%`, background: c }} /></span>
            <span className="m" style={{ width: 48, textAlign: "right" }}>{fmt(v)}</span>
            <span className="m" style={{ width: 36, textAlign: "right", color: "#5E5A52" }}>{pct((100 * v) / n, 0)}</span>
          </button>
        );
      })}
      <span style={{ fontSize: 11, color: "#5E5A52", marginTop: 4 }}>{fmt(insta)} on Instagram · {pct((100 * rows.filter((r) => r.phone || ["own", "social"].includes(webKind(r))).length) / n, 0)} reachable directly (phone, own site or social)</span>
    </div>
  );
}

function HexLegend({ layer, cut, range }: { layer: Layer; cut: Cut; range: { lo: number; hi: number } }) {
  if (layer === "off") return <span style={{ fontSize: 11, color: "#5E5A52" }}>Red circles = busiest neighbourhoods. Turn on Hexes to shade blocks by density.</span>;
  if (!isFinite(range.lo)) return null;
  const km = (n: number) => fmt(Math.round(n / HEX_KM2));
  const what = layer === "density" ? "Every block" : `${layer === "top10" ? "Top 10%" : "Top 20%"} blocks (${fmt(layer === "top10" ? cut.top10 : cut.top20)}+ merchants, of all ${fmt(cut.pool)} in the picked areas)`;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", fontSize: 11, color: "#5E5A52", alignItems: "center" }}>
      <span>{what}, coloured by merchants per block:</span>
      <span className="m">{fmt(range.lo)} <span style={{ color: "#8A8478" }}>({km(range.lo)}/km²)</span></span>
      <span style={{ width: 160, height: 10, background: `linear-gradient(90deg, ${RAMP.join(", ")})` }} />
      <span className="m">{fmt(range.hi)} <span style={{ color: "#8A8478" }}>({km(range.hi)}/km²)</span></span>
      <span>· click a block to see it up close</span>
    </div>
  );
}

function HexMerchants({ rows }: { rows: Row[] }) {
  const [more, setMore] = useState(false);
  const list = [...rows].sort((a, b) => (b.reviews || 0) - (a.reviews || 0));
  const cap = more ? 100 : 15;
  return (
    <div style={{ overflowX: "auto" }}>
      <div style={{ minWidth: 760, fontSize: 12 }}>
        <div className="m ex-merch" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
          <span>MERCHANT IN THIS HEX · {fmt(list.length)}</span><span>TYPE</span><span>★ / REVIEWS</span><span>PAYMENT</span><span>PHONE</span><span>WEBSITE</span>
        </div>
        {list.slice(0, cap).map((r, i) => (
          <div key={i} className="ex-merch" style={{ padding: "4px 0", borderBottom: "1px solid #E2DDD1" }}>
            <a className="jp" href={r.maps_uri || undefined} target="_blank" rel="noreferrer" style={{ textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</a>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.type_label}</span>
            <span className="m">{r.rating ?? "—"} · {fmt(r.reviews)}</span>
            <span>{PAY[r.pay] || r.pay}</span>
            <span className="m">{r.phone || <span style={{ color: "#A8371F" }}>—</span>}</span>
            <span>{r.web ? <a href={r.web} target="_blank" rel="noreferrer">{WEB_LABEL[webKind(r)]} ↗</a> : <span style={{ color: "#A8371F" }}>none</span>}</span>
          </div>
        ))}
        {list.length > 15 && (
          <div style={{ display: "flex", gap: 12, alignItems: "center", paddingTop: 8 }}>
            <button className="btn2" onClick={() => setMore(!more)}>{more ? "Show top 15" : `Show more (top ${Math.min(100, list.length)})`}</button>
            <span style={{ fontSize: 11, color: "#5E5A52" }}>Sorted by reviews. Use Download for all {fmt(list.length)}.</span>
          </div>
        )}
      </div>
    </div>
  );
}
