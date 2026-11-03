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

const Stat = ({ v, l, s, accent }: { v: string; l: string; s?: string; accent?: boolean }) => (
  <div style={{ padding: "12px 14px 12px 0", display: "flex", flexDirection: "column", gap: 3 }}>
    <span className="m" style={{ fontSize: 24, letterSpacing: "-0.02em", color: accent ? "#C8442B" : undefined }}>{v}</span>
    <span style={{ fontSize: 12 }}>{l}</span>
    {s && <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.45 }}>{s}</span>}
  </div>
);

/** How the chosen search terms work together: coverage, overlap, duplicates and what to drop next time. */
export function KeywordInsight({ p }: { p: Profile }) {
  const ks = p.keyword_set;
  const kws: any[] = p.keywords || [];
  if (!ks) return <KeywordYield p={p} />;
  if (!kws.length) return null;
  const dropSet = new Set(ks.drop.map((d: { keyword: string }) => d.keyword));
  const maxPer = Math.max(1, ...ks.per_place_terms.map((x: { places: number }) => x.places));
  const need = ks.terms_for_pct;

  return (
    <Card title="Keyword selection" meta={`${ks.terms} terms · coverage on the filtered list, hits and repeats on the whole run`}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(170px, 100%), 1fr))", borderTop: "1px solid #1E1E1C", borderBottom: "1px solid #D8D3C7" }}>
        <Stat v={`${fmt(ks.raw_hits)} → ${fmt(ks.unique_run)}`} l="raw hits → unique places" s={`each place came back ${ks.hits_per_unique}× on average`} />
        <Stat v={pct(ks.dupe_pct, 0)} l="of hits were duplicates" s={`${fmt(ks.repeats_same_term)} same term again (overlapping / split cells) · ${fmt(ks.found_by_several)} found by another term`} />
        <Stat v={pct(ks.multi_pct, 0)} l="places matched 2+ terms" s={`${ks.avg_terms_per_place} terms per place on average`} />
        <Stat v={`${need["90"]} / ${need["95"]}`} l={`terms for 90% / 95% coverage`} s={`all ${ks.terms} terms needed for 100%`} accent={need["95"] < ks.terms} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(380px, 100%), 1fr))", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="lbl" style={{ color: "#5E5A52" }}>Coverage curve · best term first, then the most new places each</span>
          {ks.curve.map((c: any, i: number) => (
            <div key={c.keyword} style={{ display: "grid", gridTemplateColumns: "18px minmax(70px, 120px) 1fr 56px 52px", gap: 8, alignItems: "center", fontSize: 12, opacity: dropSet.has(c.keyword) ? 0.6 : 1 }}>
              <span className="m" style={{ fontSize: 10, color: "#8A8478" }}>{i + 1}</span>
              <span className="jp" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.keyword}</span>
              <div style={{ position: "relative", height: 12, background: "#E2DDD1" }}>
                <div style={{ position: "absolute", inset: 0, width: `${c.cum_pct}%`, background: "#C9C2B2" }} />
                <div style={{ position: "absolute", top: 0, bottom: 0, left: `${c.cum_pct - (100 * c.gain) / Math.max(1, ks.places)}%`, width: `${(100 * c.gain) / Math.max(1, ks.places)}%`, background: dropSet.has(c.keyword) ? "#A39B88" : i === 0 ? "#C8442B" : "#1E1E1C", minWidth: c.gain ? 2 : 0 }} title={`+${c.gain} new places`} />
              </div>
              <span className="m" style={{ textAlign: "right" }}>+{fmt(c.gain)}</span>
              <span className="m" style={{ textAlign: "right", color: "#5E5A52" }}>{pct(c.cum_pct, c.cum_pct >= 99 && c.cum_pct < 100 ? 1 : 0)}</span>
            </div>
          ))}
          <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.5 }}>Dark segment = places this term adds that the terms above it did not find. Faded rows add under 1%.</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="lbl" style={{ color: "#5E5A52" }}>Most overlapping pairs</span>
            {ks.pairs.slice(0, 5).map((x: any) => (
              <div key={x.a + x.b} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 64px 48px", gap: 8, fontSize: 12, alignItems: "center", padding: "4px 0", borderBottom: "1px solid #E2DDD1" }}>
                <span className="jp" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.a} <span style={{ color: "#8A8478" }}>∩</span> {x.b}</span>
                <span className="m" style={{ textAlign: "right" }}>{fmt(x.both)}</span>
                <span className="m" style={{ textAlign: "right", color: x.of_smaller_pct >= 60 ? "#A8371F" : "#5E5A52" }} title="share of the smaller term's places that the other term also found">{pct(x.of_smaller_pct, 0)}</span>
              </div>
            ))}
            {!ks.pairs.length && <span style={{ fontSize: 12, color: "#5E5A52" }}>No two terms found the same place.</span>}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="lbl" style={{ color: "#5E5A52" }}>Places by number of matching terms</span>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 64, borderBottom: "1px solid #1E1E1C" }}>
              {ks.per_place_terms.map((x: any) => (
                <div key={x.terms} title={`${x.terms} term${x.terms > 1 ? "s" : ""} · ${x.places} places`} style={{ flex: 1, height: `${(100 * x.places) / maxPer}%`, background: x.terms === 1 ? "#C8442B" : "#1E1E1C", minHeight: 1 }} />
              ))}
            </div>
            <div style={{ display: "flex", gap: 4 }}>{ks.per_place_terms.map((x: any) => <span key={x.terms} className="m" style={{ flex: 1, textAlign: "center", fontSize: 9, color: "#5E5A52" }}>{x.terms}</span>)}</div>
          </div>
          <div style={{ border: "1px solid #1E1E1C", padding: 12, display: "flex", flexDirection: "column", gap: 6, background: "#F3F0E8" }}>
            <span className="m" style={{ fontSize: 10, color: "#C8442B" }}>NEXT RUN</span>
            {ks.drop.length ? (
              <span style={{ fontSize: 13, lineHeight: 1.5 }}>
                Drop <span className="jp" style={{ fontWeight: 600 }}>{ks.drop.map((d: any) => d.keyword).join("、")}</span>: together they add only {fmt(ks.drop_total.places_lost)} places
                for {fmt(ks.drop_total.calls)} calls. Saves about <span className="m">{money(ks.drop_total.saves_local)}</span>.
              </span>
            ) : (
              <span style={{ fontSize: 13, lineHeight: 1.5 }}>Every term adds at least 1% new places. Keep the selection.</span>
            )}
          </div>
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 900 }}>
          <div className="m kwi-grid" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>KEYWORD</span><span title="share of the filtered list this term found">COVERAGE</span><span title="places no other term found">ONLY THIS</span><span title="places other terms also found">SHARED</span>
            <span title="results returned across all calls, whole run">RAW HITS</span><span title="same place returned again by the same term">REPEATS</span><span title="searches with zero results">EMPTY</span>
            <span title="share of this term's places that passed the filters">KEPT</span><span>F&B</span><span>CALLS</span><span>COST</span><span title="cost per place only this term found">/ ONLY</span>
          </div>
          {kws.map((k) => (
            <div key={k.keyword} className="kwi-grid" style={{ fontSize: 12, padding: "7px 0", borderBottom: "1px solid #E2DDD1", alignItems: "center", opacity: dropSet.has(k.keyword) ? 0.65 : 1 }}>
              <span className="jp" style={{ fontSize: 13 }} title={k.top_types?.join(" · ")}>{k.keyword}</span>
              <span style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <span className="m">{pct(k.coverage_pct, 0)} <span style={{ color: "#8A8478" }}>{fmt(k.places)}</span></span>
                <span style={{ height: 3, background: "#1E1E1C", width: `${k.coverage_pct}%` }} />
              </span>
              <span className="m" style={{ color: k.only_pct < 5 ? "#A8371F" : "#5E7D4A" }}>{fmt(k.only_this)}</span>
              <span className="m">{fmt(k.shared)}</span>
              <span className="m">{fmt(k.hits)}</span>
              <span className="m">{fmt(k.repeats)} <span style={{ color: "#8A8478" }}>{pct(k.repeat_pct, 0)}</span></span>
              <span className="m" style={{ color: k.empty_pct > 30 ? "#A8371F" : undefined }}>{pct(k.empty_pct, 0)}</span>
              <span className="m">{pct(k.kept_pct, 0)}</span>
              <span className="m" style={{ color: k.fnb_pct < 90 ? "#A8371F" : undefined }}>{pct(k.fnb_pct, 0)}</span>
              <span className="m">{fmt(k.calls)}</span>
              <span className="m">{k.cost_local != null ? money(k.cost_local) : "—"}</span>
              <span className="m">{k.cost_per_unique != null ? money(k.cost_per_unique) : "—"}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
