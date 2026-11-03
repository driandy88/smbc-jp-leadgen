import { Fragment, useEffect, useMemo, useState } from "react";
import { api, ApiError, download } from "../../api";
import { HexMap, Outline } from "../../components/HexMap";
import { PlaceMap, Points } from "../../components/PlaceMap";
import { Squiggle } from "../../components/Icons";
import { cityName, fmt, pct, shortDate, money } from "../../lib/format";
import { AiBrief, Brief } from "./AiBrief";
import { FnbCheck, HexBreakdown, KeywordInsight } from "./Breakdown";
import { binLayers, CASH, CAT_COLORS, Legend, PRICE_COLORS, VBars } from "./charts";
import { Profile, Version } from "./types";

type Analysis = { profile: Profile; summary: Brief };

export function Analysis({ onDataChip }: { onDataChip: (s: string) => void }) {
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [result, setResult] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [outline, setOutline] = useState<Outline | null>(null);

  useEffect(() => {
    api<Version[]>("/api/versions").then((v) => {
      setVersions(v);
      if (v[0]) setSel(v[0].id);
    });
  }, []);

  const v = versions?.find((x) => x.id === sel) || null;
  useEffect(() => {
    setResult(null);
    setErr("");
    if (!v) return;
    onDataChip(v.name);
    if (v.analyzed) api<Analysis>(`/api/versions/${v.id}/analysis`).then((a) => a.profile && setResult(a));
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const areas = result?.profile?.run?.areas;
    if (areas) api<Outline>("/api/scout/geometry", { body: areas.map((a: { area: string }) => a.area) }).then(setOutline);
  }, [result]);

  const analyze = async () => {
    if (!v) return;
    setBusy(true);
    setErr("");
    try {
      setResult(await api<Analysis>(`/api/versions/${v.id}/analyze`, { method: "POST" }));
      setVersions((vs) => vs && vs.map((x) => (x.id === v.id ? { ...x, analyzed: true } : x)));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  };

  if (!versions) return null;
  if (!versions.length) return <div style={{ padding: "40px 0", color: "#5E5A52", fontSize: 14 }}>No saved versions yet. Run a retrieval, filter it and save it from the Summary step.</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 1000 }}>
          <div className="m vrow" style={{ cursor: "default", fontSize: 10, color: "#5E5A52", letterSpacing: "0.05em", borderTop: "1px solid #1E1E1C", minHeight: 36, padding: 8 }}>
            <span /><span>VERSION</span><span>DATE</span><span>CITIES</span><span style={{ textAlign: "right" }}>AREAS</span><span style={{ textAlign: "right" }}>KW</span><span style={{ textAlign: "right" }}>ROWS</span><span style={{ textAlign: "right" }}>DIFF</span><span style={{ textAlign: "right" }}>API COST</span><span>AUTHOR</span>
          </div>
          {versions.map((x, i) => (
            <button key={x.id} className="vrow" aria-pressed={x.id === sel} onClick={() => setSel(x.id)} title={x.notes}>
              <span className="rad">{x.id === sel && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#C8442B" }} />}</span>
              <span className="m" style={{ display: "flex", gap: 8, alignItems: "center", overflow: "hidden" }}>{x.name}{i === 0 && <span className="latest">latest</span>}{x.mock && <span className="mock-tag">mock</span>}</span>
              <span className="m">{shortDate(x.created_at)}</span><span>{x.cities.map(cityName).join(", ")}</span>
              <span className="m" style={{ textAlign: "right" }}>{x.areas}</span><span className="m" style={{ textAlign: "right" }}>{x.keywords}</span>
              <span className="m" style={{ textAlign: "right" }}>{fmt(x.rows)}</span>
              <span className="m" style={{ textAlign: "right", color: (x.diff ?? 0) >= 0 ? "#5E7D4A" : "#B33A3A" }}>{x.diff == null ? "—" : `${x.diff >= 0 ? "+" : ""}${fmt(x.diff)}`}</span>
              <span className="m" style={{ textAlign: "right" }}>{x.mock ? `(${money(x.cost_local)})` : money(x.cost_local)}</span>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{x.author.split("@")[0]}</span>
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: "#5E5A52" }}>Selected <span className="m" style={{ color: "#1E1E1C" }}>{v?.name}</span> · {fmt(v?.rows)} rows{v?.notes ? ` · ${v.notes}` : ""}</span>
        <div style={{ display: "flex", gap: 8 }}>
          {v && <button className="btn2" onClick={() => download(`/api/versions/${v.id}/export.csv`, `${v.name}.csv`)}>Export CSV</button>}
          <button className="btn" onClick={analyze} disabled={!v || busy}>{result ? "Re-analyze" : "Analyze"}</button>
        </div>
      </div>
      {err && <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>}

      {busy && (
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "40px 0", justifyContent: "center" }}>
          <Squiggle w={160} /><span style={{ fontSize: 13, color: "#5E5A52" }}>Profiling {fmt(v?.rows)} rows{v?.mock ? "" : " and asking Claude"}…</span>
        </div>
      )}

      {result && !busy && v && <Report key={v.id} a={result} versionId={v.id} name={v.name} outline={outline} />}
    </div>
  );
}

function Report({ a, versionId, name, outline }: { a: Analysis; versionId: number; name: string; outline: Outline | null }) {
  const [points, setPoints] = useState<Points | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  useEffect(() => { api<Points>(`/api/versions/${versionId}/points`).then(setPoints); }, [versionId]);
  const p = a.profile;
  const s = a.summary;
  const cashLayers = useMemo(() => binLayers(p.cash_hex as { h: string; share: number }[], (c) => c.share, [0.2, 0.3, 0.4, 0.5], CASH), [p]);
  const maxHeat = Math.max(0.01, ...p.open_heat.flatMap((r: { c: number[] }) => r.c));

  return (
    <div className="hx-in" style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <AiBrief s={s} name={name} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))", borderTop: "1px solid #1E1E1C", borderBottom: "1px solid #D8D3C7" }}>
        {Object.entries(p.segments).map(([k, sg]: [string, any]) => (
          <div key={k} style={{ padding: "18px 16px", display: "flex", flexDirection: "column", gap: 6, borderRight: "1px solid #E2DDD1" }}>
            <span className="m" style={{ fontSize: 30, letterSpacing: "-0.02em", color: k === "priority" ? "#C8442B" : undefined }}>{fmt(sg.n)}</span>
            <span style={{ fontSize: 13 }}>{{ priority: "Priority leads", card_gap: "Card-acceptance gap", digital_gap: "Digital gap", new_or_small: "New or low-traffic" }[k]} <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{pct(sg.pct)}</span></span>
            <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.5 }}>{sg.def}</span>
          </div>
        ))}
      </div>

      <Card title="Merchant map · every place in this version" meta={`hexes at res ${p.run.base_res}`}>
        <PlaceMap points={points} outline={outline} res={p.run.base_res} highlight={hover} />
      </Card>

      <HexBreakdown p={p} res={p.run.base_res} onHover={setHover} />
      <KeywordInsight p={p} />
      <FnbCheck p={p} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(380px, 100%), 1fr))", gap: 24 }}>
        <Card title="Area ranking · where to send reps" meta="operational places">
          <div style={{ overflowX: "auto" }}>
            <div style={{ minWidth: 330 }}>
              <div className="m area-grid" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}><span>AREA</span><span>PLACES</span><span>/KM²</span><span>CASH/NONE</span><span>NO WEB</span><span>LEADS</span></div>
              {[...p.areas].sort((x: any, y: any) => y.priority_leads - x.priority_leads).slice(0, 12).map((ar: any) => (
                <div key={ar.code} className="m area-grid" style={{ fontSize: 12, padding: "7px 0", borderBottom: "1px solid #E2DDD1" }}>
                  <span className="jp" style={{ fontFamily: "'Noto Sans JP', sans-serif" }}>{ar.jp}</span><span>{fmt(ar.places)}</span><span>{fmt(ar.per_km2)}</span>
                  <span>{pct(ar.cash_or_unknown_pct, 0)}</span><span>{pct(ar.no_website_pct, 0)}</span><span style={{ color: "#C8442B" }}>{fmt(ar.priority_leads)}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card title="Top priority leads" meta="most reviewed first">
          {p.top_leads.length === 0 && <span style={{ fontSize: 12, color: "#5E5A52" }}>No places match the priority definition.</span>}
          {p.top_leads.slice(0, 10).map((l: any, i: number) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 70px 46px 56px", gap: 8, fontSize: 12, padding: "6px 0", borderBottom: "1px solid #E2DDD1", alignItems: "center" }}>
              <a className="jp" href={l.maps_uri} target="_blank" rel="noreferrer" style={{ textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.name}</a>
              <span className="jp" style={{ color: "#5E5A52" }}>{l.area}</span><span className="m">★{l.rating}</span><span className="m" style={{ textAlign: "right" }}>{fmt(l.reviews)}</span>
            </div>
          ))}
        </Card>

        <Card title="Rating distribution" meta={`median ${p.overview.median_rating ?? "—"} · unrated ${fmt(p.overview.unrated)}`}>
          <VBars data={p.rating_hist.map((b: { l: string; v: number }) => ({ ...b, c: parseFloat(b.l) >= 3.5 || b.l === "4.3+" ? "#1E1E1C" : "#A39B88" }))} />
        </Card>

        <Card title="Review count · log bins" meta={`median ${fmt(p.overview.median_reviews)} · p75 ${fmt(p.overview.p75_reviews)}`}>
          <VBars data={p.review_hist} />
        </Card>

        <Card title="Price level by area" meta="share of places">
          {p.areas.slice(0, 9).map((ar: any) => (
            <div key={ar.code} style={{ display: "grid", gridTemplateColumns: "96px 1fr", gap: 10, alignItems: "center" }}>
              <span className="jp" style={{ fontSize: 12 }}>{ar.jp}</span>
              <div style={{ display: "flex", height: 14, gap: 1 }}>{ar.price.map((w: number, i: number) => <span key={i} title={`${p.price_bands[i]} · ${w}%`} style={{ height: 14, width: `${w}%`, background: PRICE_COLORS[i], outline: i === 5 ? "1px solid #D8D3C7" : undefined }} />)}</div>
            </div>
          ))}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", paddingTop: 4 }}>{p.price_bands.map((l: string, i: number) => <span key={l} className="m" style={{ display: "inline-flex", gap: 5, alignItems: "center", fontSize: 10, color: "#5E5A52" }}><span style={{ width: 8, height: 8, background: PRICE_COLORS[i], border: "1px solid #D8D3C7" }} />{l}</span>)}</div>
        </Card>

        <Card title="Category share by area" meta="% of area">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(96px, 1fr))", gap: "14px 12px" }}>
            {p.type_by_area.map((ar: any) => (
              <div key={ar.area} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="jp" style={{ fontSize: 11, fontWeight: 600 }}>{ar.area}</span>
                {p.top_types.map((t: string, i: number) => <div key={t} title={`${t} · ${ar.shares[t]}%`} style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ height: 6, width: `${Math.max(2, ar.shares[t])}%`, background: CAT_COLORS[i] }} /><span className="m" style={{ fontSize: 9, color: "#5E5A52" }}>{Math.round(ar.shares[t])}</span></div>)}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>{p.top_types.map((t: string, i: number) => <span key={t} className="jp" style={{ display: "inline-flex", gap: 5, alignItems: "center", fontSize: 10, color: "#5E5A52" }}><span style={{ width: 8, height: 8, background: CAT_COLORS[i] }} />{t}</span>)}</div>
        </Card>

        <Card title="Cash-only or no card info · by hex" meta="cells with 3+ operational places">
          <HexMap outline={outline} layers={cashLayers} height={340} ariaLabel="Hex map of cash-only share" />
          <Legend title="share" colors={CASH} labels="<20 · 30 · 40 · 50%+" />
        </Card>

        <Card title="Open now · weekday × hour" meta="share of places open (JST)">
          <div style={{ display: "grid", gridTemplateColumns: "30px repeat(24, minmax(0, 1fr))", gap: 2, alignItems: "center" }}>
            <span />
            {Array.from({ length: 24 }, (_, h) => <span key={h} className="m" style={{ fontSize: 8, color: "#5E5A52", textAlign: "center" }}>{h % 3 === 0 ? h : ""}</span>)}
            {p.open_heat.map((r: { d: string; c: number[] }) => (
              <Fragment key={r.d}>
                <span className="m" style={{ fontSize: 10, color: "#5E5A52" }}>{r.d}</span>
                {r.c.map((v, h) => <span key={h} className="hm" title={`${r.d} ${h}:00 · ${Math.round(v * 100)}% open`} style={{ background: `rgba(30,30,28,${(0.06 + 0.94 * v / maxHeat).toFixed(3)})` }} />)}
              </Fragment>
            ))}
          </div>
          <span className="m" style={{ fontSize: 10, color: "#5E5A52" }}>Peak {p.open_peak.day} {p.open_peak.hour}:00 · {Math.round(p.open_peak.share * 100)}% open. Quietest weekday visit hour: {(() => { const q = [...p.visit_window].sort((x: any, y: any) => x.open_share - y.open_share)[0]; return q ? `${q.hour}:00 (${Math.round(q.open_share * 100)}% open)` : "—"; })()}</span>
        </Card>

        <Card title="Data completeness by field" meta="% non-null">
          {p.completeness.map((c: { field: string; pct: number }) => (
            <div key={c.field} style={{ display: "grid", gridTemplateColumns: "170px 1fr 44px", gap: 10, alignItems: "center" }}>
              <span className="m" style={{ fontSize: 11 }}>{c.field}</span>
              <div style={{ height: 6, background: "#E2DDD1" }}><div style={{ height: 6, width: `${c.pct}%`, background: c.pct < 50 ? "#C8442B" : "#1E1E1C" }} /></div>
              <span className="m" style={{ fontSize: 11, textAlign: "right" }}>{Math.round(c.pct)}%</span>
            </div>
          ))}
        </Card>

        <Card title="Data quality" meta="">
          {[
            { l: "Permanently closed", d: "still listed on Google; kept only if not filtered", v: pct(p.quality.perm_closed_pct), bad: p.quality.perm_closed_pct > 5 },
            { l: "No opening hours", d: "cannot plan visit windows", v: pct(p.quality.no_hours_pct), bad: p.quality.no_hours_pct > 20 },
            { l: "Likely chains", d: "brand with 3+ branches; central purchasing", v: pct(p.quality.chain_pct), bad: false },
            { l: "Duplicates merged", d: "same place_id across keywords and hexes", v: fmt(p.quality.duplicates_merged), bad: false },
            { l: "Saturated cells", d: "60 results even at max resolution", v: fmt(p.quality.saturated_cells), bad: p.quality.saturated_cells > 0 },
            { l: "Matched 2+ keywords", d: "overlap between search terms", v: pct(p.quality.multi_keyword_pct), bad: false },
          ].map((q) => (
            <div key={q.l} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16, padding: "10px 0", borderTop: "1px solid #E2DDD1" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}><span style={{ fontSize: 13 }}>{q.l}</span><span style={{ fontSize: 11, color: "#5E5A52" }}>{q.d}</span></div>
              <span className="m" style={{ fontSize: 20, color: q.bad ? "#B33A3A" : "#1E1E1C" }}>{q.v}</span>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}

function Card({ title, meta, children }: { title: string; meta: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><span className="lbl">{title}</span><span className="m" style={{ fontSize: 11, color: "#5E5A52", textAlign: "right" }}>{meta}</span></div>
      {children}
    </div>
  );
}
