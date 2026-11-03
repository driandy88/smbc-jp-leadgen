import { useEffect, useState } from "react";
import { api, ApiError } from "../../api";
import type { Outline } from "../../components/HexMap";
import { PlaceMap, Points } from "../../components/PlaceMap";
import { Squiggle } from "../../components/Icons";
import { cityName, fmt, pct } from "../../lib/format";
import { FnbCheck, KeywordInsight } from "./Breakdown";
import { Contactability, Insights, MerchantMix } from "./MerchantSummary";
import { ContactSlicer, FnbSegments, Hotspots } from "./Business";
import { CAT_COLORS } from "./charts";
import { Filters, Profile, Run, Version } from "./types";

type ResultData = { count: number; profile: Profile; cities: { city: string; places: number; cash_or_unknown_pct: number; median_rating: number | null; median_reviews: number | null }[]; run: Run };

export function Result({ runId, filters, onSaved, onNext, onBack }: { runId: number; filters: Partial<Filters>; onSaved: (name: string) => void; onNext: () => void; onBack: () => void }) {
  const [data, setData] = useState<ResultData | null>(null);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState<Version | null>(null);
  const [err, setErr] = useState("");
  const [points, setPoints] = useState<Points | null>(null);

  useEffect(() => {
    api<ResultData>(`/api/runs/${runId}/result`, { body: filters }).then((d) => {
      setData(d);
      if (d.run) api<Outline>("/api/scout/geometry", { body: d.run.areas.map((a) => a.area) }).then(setOutline);
    });
    api<{ name: string }>(`/api/versions/next-name?run_id=${runId}`).then((r) => setName(r.name));
    setPoints(null);
    api<Points>(`/api/runs/${runId}/points`, { body: filters }).then(setPoints);
  }, [runId, filters]);

  const p = data?.profile;

  if (!data) return <div style={{ display: "flex", gap: 14, alignItems: "center", padding: 40 }}><Squiggle w={120} /><span style={{ fontSize: 13, color: "#5E5A52" }}>Summarising…</span></div>;
  if (!data.count) return <div style={{ padding: 40 }}>No places left after filtering. <button className="btn2" onClick={onBack}>← Back to Filter</button></div>;

  const o = p.overview;
  const run = data.run;
  const cashPct = p.payment.cash.pct + p.payment.none.pct;
  const topArea = [...p.areas].sort((a: any, b: any) => b.cash_or_unknown_pct - a.cash_or_unknown_pct).find((a: any) => a.places >= 20 && a.code !== "outside");
  // With one ward there is nothing to compare it against
  const several = p.areas.filter((a: any) => a.code !== "outside").length > 1;
  const stats = [
    { v: fmt(data.count), l: "unique merchants after filter", s: `${fmt(p.fnb?.core?.n)} F&B · ${fmt(run.raw_hits)} raw hits · ${fmt(run.unique_places - data.count)} filtered out` },
    { v: pct(cashPct), l: "cash-only or no card info", s: `${pct(p.payment.cash.pct)} explicit cash-only · ${pct(p.payment.none.pct)} no payment data` },
    { v: o.median_rating?.toFixed(1) ?? "—", l: "median rating", s: `median ${fmt(o.median_reviews)} reviews · ${fmt(o.unrated)} unrated kept` },
    { v: p.hotspots?.[0] ? fmt(p.hotspots[0].density_km2) : "—", l: "merchants / km² in the densest spot", s: p.hotspots?.[0] ? `${p.hotspots[0].name} (${p.hotspots[0].ward}) · ${fmt(p.hotspots[0].n)} within 400 m` : "" },
    { v: fmt(run.dupes), l: "duplicates merged", s: "same place_id across keywords and hexes" },
  ];
  const insights = [
    topArea && { k: "01", t: several
      ? `${topArea.en} is the strongest cash pocket: ${pct(topArea.cash_or_unknown_pct)} cash-only or no card info, against ${pct(cashPct)} overall.`
      : `${pct(cashPct)} of ${topArea.en} merchants are cash-only or show no card info (${pct(p.payment.cash.pct)} explicitly cash-only).` },
    p.contact && { k: "02", t: `${fmt(p.contact.cash_callable.n)} of ${fmt(p.contact.cash_callable.of)} cash-only / no-card merchants list a phone number: that is the call list. ${pct(p.contact.either_pct, 0)} of all merchants are reachable by phone or website.` },
    { k: "03", t: run.saturated ? `${fmt(run.saturated)} cells still hit 60 results at res ${run.max_res}; raise the max split resolution to recover them.` : `${fmt(run.splits)} busy cells were split down to res ${run.max_res}; none stayed saturated.` },
  ].filter(Boolean) as { k: string; t: string }[];

  const save = async () => {
    setErr("");
    try {
      const v = await api<Version>("/api/versions", { body: { run_id: runId, name, notes, filters } });
      setSaved(v);
      onSaved(v.name);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Save failed");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(200px, 100%), 1fr))", borderTop: "1px solid #1E1E1C", borderBottom: "1px solid #D8D3C7" }}>
        {stats.map((s) => (
          <div key={s.l} style={{ padding: "20px 18px", display: "flex", flexDirection: "column", gap: 6, borderRight: "1px solid #E2DDD1" }}>
            <span className="m" style={{ fontSize: 34, letterSpacing: "-0.02em" }}>{s.v}</span>
            <span style={{ fontSize: 13 }}>{s.l}</span>
            <span className="m" style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.5, wordBreak: "break-all" }}>{s.s}</span>
          </div>
        ))}
      </div>

      <Insights p={p} />

      <div className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}><span className="lbl">Merchant map · every place after filtering</span><span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>red circles = densest neighbourhoods</span></div>
        <PlaceMap points={points} outline={outline} hotspots={p.hotspots} />
      </div>

      <Hotspots p={p} />
      <FnbSegments p={p} />
      <MerchantMix p={p} />
      <Contactability p={p} />
      <ContactSlicer points={points} />

      <div style={{ display: "flex", flexWrap: "wrap", gap: 24, alignItems: "stretch" }}>
        <div style={{ flex: "1 1 420px", minWidth: 0, display: "flex", flexDirection: "column", gap: 22 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <span className="lbl">Category share · primaryType</span>
            <div style={{ display: "flex", height: 22, gap: 2 }}>
              {p.types.map((c: any, i: number) => <span key={c.label} title={`${c.label} · ${c.n}`} style={{ height: 22, width: `${c.pct}%`, background: CAT_COLORS[i % CAT_COLORS.length] }} />)}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(190px, 100%), 1fr))", gap: "6px 16px" }}>
              {p.types.map((c: any, i: number) => (
                <div key={c.label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                  <span style={{ width: 9, height: 9, background: CAT_COLORS[i % CAT_COLORS.length], flex: "0 0 auto" }} /><span className="jp">{c.label}</span><span className="m" style={{ marginLeft: "auto" }}>{fmt(c.n)}</span>
                </div>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", borderTop: "1px solid #D8D3C7" }}>
            {insights.map((i) => <div key={i.k} style={{ display: "flex", gap: 14, padding: "12px 0", borderBottom: "1px solid #E2DDD1", fontSize: 14, lineHeight: 1.5 }}><span className="m" style={{ fontSize: 11, color: "#C8442B", paddingTop: 3 }}>{i.k}</span><span>{i.t}</span></div>)}
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span className="lbl" style={{ paddingBottom: 8 }}>City comparison</span>
            <div className="m cmp-grid" style={{ fontSize: 10, color: "#5E5A52", letterSpacing: "0.05em", padding: "6px 0", borderBottom: "1px solid #1E1E1C" }}><span>CITY</span><span>PLACES</span><span>CASH / NO INFO</span><span>MED. RATING</span><span>MED. REVIEWS</span></div>
            {data.cities.map((c) => (
              <div key={c.city} className="m cmp-grid" style={{ fontSize: 13, padding: "10px 0", borderBottom: "1px solid #E2DDD1" }}>
                <span style={{ fontFamily: "'Inter Tight', sans-serif" }}>{cityName(c.city)}</span><span>{fmt(c.places)}</span><span>{pct(c.cash_or_unknown_pct)}</span><span>{c.median_rating?.toFixed(1) ?? "—"}</span><span>{fmt(c.median_reviews)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <KeywordInsight p={p} />
      <FnbCheck p={p} />

      <div className="card" style={{ position: "relative", padding: 22, display: "flex", flexWrap: "wrap", gap: "20px 32px", alignItems: "flex-end", overflow: "hidden" }}>
        <div style={{ flex: "1 1 280px", display: "flex", flexDirection: "column", gap: 6 }}>
          <label htmlFor="hx-vn" className="lbl">Version name</label>
          <input id="hx-vn" className="in m" value={name} onChange={(e) => setName(e.target.value)} disabled={!!saved} style={{ fontSize: 14 }} />
        </div>
        <div style={{ flex: "2 1 360px", display: "flex", flexDirection: "column", gap: 6 }}>
          <label htmlFor="hx-vnote" className="lbl">Notes</label>
          <input id="hx-vnote" className="in" placeholder="What changed in this pull?" value={notes} onChange={(e) => setNotes(e.target.value)} disabled={!!saved} />
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn2" onClick={onBack}>← Filter</button>
          {!saved ? <button className="btn" onClick={save} disabled={!name.trim()}>Save version</button> : (
            <>
              <span className="m" style={{ fontSize: 12, color: "#5E5A52", paddingRight: 80 }}>saved · {fmt(saved.rows)} rows{saved.diff != null ? ` · ${saved.diff >= 0 ? "+" : ""}${fmt(saved.diff)} vs previous` : ""}</span>
              <button className="btn" onClick={onNext}>Versions &amp; analysis →</button>
            </>
          )}
        </div>
        {err && <span role="alert" style={{ fontSize: 12, color: "#B33A3A", width: "100%" }}>{err}</span>}
        {saved && (
          <div aria-hidden="true" style={{ position: "absolute", right: 236, top: 14, width: 64, height: 64 }}>
            <span className="hx-ink" style={{ position: "absolute", inset: -6, borderRadius: "50%", background: "#C8442B" }} />
            <span className="hx-stamp stamp">
              <span className="serif" style={{ fontSize: 26, lineHeight: 1, fontWeight: 600 }}>v{saved.name.match(/_v(\d+)$/)?.[1] || saved.id}</span>
              <span className="m" style={{ fontSize: 7, letterSpacing: "0.1em" }}>{new Date().toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" }).replace("/", "·")}</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
