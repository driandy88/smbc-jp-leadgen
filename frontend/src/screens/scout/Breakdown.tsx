import { fmt, money, pct } from "../../lib/format";
import { Profile } from "./types";

const Card = ({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) => (
  <div className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span className="lbl">{title}</span>
      {meta && <span className="m" style={{ fontSize: 11, color: "#5E5A52", textAlign: "right" }}>{meta}</span>}
    </div>
    {children}
  </div>
);

/** Is it really F&B? Google has no flag, so we read primaryType, types and dining attributes. */
export function FnbCheck({ p }: { p: Profile }) {
  const f = p.fnb;
  if (!f) return null;
  const parts = [
    { k: "core", l: "F&B", c: "#1E1E1C", d: "primaryType is food or drink" },
    { k: "related", l: "F&B-related", c: "#C8442B", d: "other primaryType, but food in types or dining attributes" },
    { k: "no", l: "Not F&B", c: "#C9C2B2", d: "no food signal" },
  ];
  return (
    <Card title="F&B check" meta="from primaryType · types · dineIn / serves*">
      <div style={{ display: "flex", height: 14, gap: 2 }}>
        {parts.map((x) => <span key={x.k} title={`${x.l} · ${f[x.k].n}`} style={{ width: `${f[x.k].pct}%`, background: x.c, minWidth: f[x.k].n ? 3 : 0 }} />)}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 }}>
        {parts.map((x) => (
          <div key={x.k} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <span className="m" style={{ fontSize: 22 }}>{fmt(f[x.k].n)}</span>
            <span style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "center" }}><span style={{ width: 8, height: 8, background: x.c }} />{x.l} <span className="m" style={{ color: "#5E5A52", fontSize: 11 }}>{pct(f[x.k].pct)}</span></span>
            <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.4 }}>{x.d}</span>
          </div>
        ))}
      </div>
      {f.non_core_types.length > 0 && (
        <div style={{ fontSize: 12, color: "#5E5A52", borderTop: "1px solid #E2DDD1", paddingTop: 10, lineHeight: 1.6 }}>
          Not core F&B: {f.non_core_types.map((t: { type: string; n: number }) => <span key={t.type} className="jp" style={{ marginRight: 10, color: "#1E1E1C" }}>{t.type} <span className="m" style={{ color: "#5E5A52" }}>{t.n}</span></span>)}
        </div>
      )}
    </Card>
  );
}

/** What each search term bought: places found, F&B purity, and places no other term found. */
export function KeywordYield({ p }: { p: Profile }) {
  const kws: any[] = p.keywords || [];
  if (!kws.length) return null;
  const max = Math.max(1, ...kws.map((k) => k.places));
  return (
    <Card title="Keyword yield" meta="only this = places no other term found">
      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 560 }}>
          <div className="m kw-grid" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>KEYWORD</span><span>PLACES</span><span>F&B</span><span>ONLY THIS</span><span>CALLS</span><span>COST / UNIQUE</span><span>TOP TYPES</span>
          </div>
          {kws.map((k) => (
            <div key={k.keyword} className="kw-grid" style={{ fontSize: 12, padding: "8px 0", borderBottom: "1px solid #E2DDD1", alignItems: "center" }}>
              <span className="jp" style={{ fontSize: 13 }}>{k.keyword}</span>
              <span style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <span className="m">{fmt(k.places)}</span>
                <span style={{ height: 3, background: "#1E1E1C", width: `${(100 * k.places) / max}%` }} />
              </span>
              <span className="m" style={{ color: k.fnb_pct < 90 ? "#A8371F" : undefined }}>{pct(k.fnb_pct, 0)}</span>
              <span className="m" style={{ color: k.only_pct < 10 ? "#A8371F" : "#5E7D4A" }}>{fmt(k.only_this)} <span style={{ color: "#8A8478" }}>({pct(k.only_pct, 0)})</span></span>
              <span className="m">{fmt(k.calls)}</span>
              <span className="m">{k.cost_per_unique != null ? money(k.cost_per_unique) : "—"}</span>
              <span className="jp" style={{ fontSize: 11, color: "#5E5A52", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{k.top_types.join(" · ")}</span>
            </div>
          ))}
        </div>
      </div>
      <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.5 }}>A term with a low "only this" share mostly re-finds places other terms already cover; dropping it saves calls.</span>
    </Card>
  );
}

/** Merchants per hex at the base resolution, densest first. */
export function HexBreakdown({ p, res, onHover }: { p: Profile; res: number; onHover?: (h: string | null) => void }) {
  const hx = p.hexes;
  if (!hx) return null;
  const stats = [
    { v: fmt(hx.cells), l: "hexes with merchants" },
    { v: fmt(hx.median), l: "median per hex" },
    { v: fmt(hx.p90), l: "p90 per hex" },
    { v: pct(hx.top10_share, 0), l: `in top ${hx.top10_cells} hexes (10%)` },
  ];
  return (
    <Card title={`Hex breakdown · res ${res}`} meta="densest first · hover to locate">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", borderTop: "1px solid #1E1E1C", borderBottom: "1px solid #D8D3C7" }}>
        {stats.map((s, i) => (
          <div key={s.l} style={{ padding: "10px 10px 10px 0", paddingLeft: i ? 10 : 0, borderLeft: i ? "1px solid #E2DDD1" : undefined, display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="m" style={{ fontSize: 20 }}>{s.v}</span><span style={{ fontSize: 11, color: "#5E5A52" }}>{s.l}</span>
          </div>
        ))}
      </div>
      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 720 }}>
          <div className="m hex-grid" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>HEX</span><span>AREA</span><span>MERCHANTS</span><span>F&B</span><span>MERCHANT TYPES</span><span>CASH/NONE</span><span>★</span><span>LEADS</span>
          </div>
          {hx.rows.map((r: any) => (
            <div key={r.h} className="hex-grid hex-row" onMouseEnter={() => onHover?.(r.h)} onMouseLeave={() => onHover?.(null)}>
              <span className="m" style={{ fontSize: 10.5 }}>{r.h}</span>
              <span className="jp">{r.area}</span>
              <span className="m">{fmt(r.places)}</span>
              <span className="m">{fmt(r.fnb)} <span style={{ color: "#8A8478", fontSize: 10 }}>{Math.round((100 * r.fnb) / r.places)}%</span></span>
              <span style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {r.types.map((t: { t: string; n: number }) => <span key={t.t} className="jp type-chip">{t.t} <span className="m">{t.n}</span></span>)}
              </span>
              <span className="m">{pct(r.cash_pct, 0)}</span>
              <span className="m">{r.median_rating ?? "—"}</span>
              <span className="m" style={{ color: r.leads ? "#C8442B" : "#8A8478" }}>{fmt(r.leads)}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
