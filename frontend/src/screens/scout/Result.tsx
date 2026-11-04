import { useEffect, useState } from "react";
import { api, ApiError } from "../../api";
import { Squiggle } from "../../components/Icons";
import { fmt, pct } from "../../lib/format";
import { Filters, Profile, Run, Version } from "./types";

type ResultData = { count: number; profile: Profile; run: Run };
type Explanation = { headline: string; summary: string; points: { topic: string; text: string }[]; source: string };

/** Summary step: the headline numbers and an AI read of them. The detail lives in Versions → Analysis. */
export function Result({ runId, filters, onSaved, onNext, onBack }: { runId: number; filters: Partial<Filters>; onSaved: (name: string) => void; onNext: () => void; onBack: () => void }) {
  const [data, setData] = useState<ResultData | null>(null);
  const [ai, setAi] = useState<Explanation | null>(null);
  const [aiErr, setAiErr] = useState("");
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState<Version | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    setAi(null);
    setAiErr("");
    api<ResultData>(`/api/runs/${runId}/result`, { body: filters }).then((d) => {
      setData(d);
      if (d.count) api<Explanation>(`/api/runs/${runId}/explain`, { body: filters }).then(setAi).catch((e) => setAiErr(e instanceof ApiError ? e.message : "Could not write the summary"));
    });
    api<{ name: string }>(`/api/versions/next-name?run_id=${runId}`).then((r) => setName(r.name));
  }, [runId, filters]);

  const p = data?.profile;

  if (!data) return <div style={{ display: "flex", gap: 14, alignItems: "center", padding: 40 }}><Squiggle w={120} /><span style={{ fontSize: 13, color: "#5E5A52" }}>Summarising…</span></div>;
  if (!data.count) return <div style={{ padding: 40 }}>No places left after filtering. <button className="btn2" onClick={onBack}>← Back to Filter</button></div>;

  const o = p.overview;
  const run = data.run;
  const c = p.contact;
  const dense = (p.areas || []).filter((a: any) => a.per_km2 != null).sort((a: any, b: any) => b.per_km2 - a.per_km2)[0];
  const stats = [
    { v: fmt(data.count), l: "F&B merchants", s: `incl. ${fmt(p.fnb?.related?.n)} F&B-related venues · ${fmt(run.unique_places - data.count)} places filtered out` },
    { v: c ? pct(c.either_pct, 0) : "—", l: "reachable by phone or web", s: c ? `${fmt(c.phone)} phone · ${fmt(c.web)} website · ${fmt(c.neither)} neither` : "" },
    { v: pct(o.cash_or_unknown_pct, 0), l: "cash-only or no card info", s: c ? `${fmt(c.cash_callable.n)} of them list a phone` : "" },
    { v: o.median_rating?.toFixed(1) ?? "—", l: "median rating", s: `median ${fmt(o.median_reviews)} reviews` },
    { v: dense ? fmt(Math.round(dense.per_km2)) : "—", l: "F&B / km² in the densest area", s: dense ? dense.en : "" },
  ];

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
        {stats.map((s, i) => (
          <div key={s.l} style={{ padding: "20px 18px", display: "flex", flexDirection: "column", gap: 6, borderRight: "1px solid #E2DDD1" }}>
            <span className="m" style={{ fontSize: 34, letterSpacing: "-0.02em", color: i === 1 ? "#C8442B" : undefined }}>{s.v}</span>
            <span style={{ fontSize: 13 }}>{s.l}</span>
            <span className="m" style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.5 }}>{s.s}</span>
          </div>
        ))}
      </div>

      <section className="card" aria-label="AI summary" aria-busy={!ai && !aiErr} style={{ padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
        <span className="m ai-tag" style={{ alignSelf: "flex-start" }}>AI SUMMARY</span>
        {!ai && !aiErr && <div style={{ display: "flex", gap: 14, alignItems: "center" }}><Squiggle w={90} /><span style={{ fontSize: 13, color: "#5E5A52" }}>Reading the numbers…</span></div>}
        {aiErr && <span role="alert" style={{ fontSize: 13, color: "#B33A3A" }}>{aiErr}</span>}
        {ai && (
          <>
            <h2 className="serif" style={{ margin: 0, fontWeight: 400, fontSize: 28, lineHeight: 1.2 }}>{ai.headline}</h2>
            <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "#3A3833", maxWidth: 860 }}>{ai.summary}</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(320px, 100%), 1fr))", gap: "0 28px" }}>
              {ai.points.map((x, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "76px 1fr", gap: 12, padding: "11px 0", borderTop: "1px solid #E2DDD1", fontSize: 13, lineHeight: 1.55 }}>
                  <span className="m" style={{ fontSize: 10, color: "#C8442B", paddingTop: 3, letterSpacing: "0.05em" }}>{x.topic.toUpperCase()}</span>
                  <span>{x.text}</span>
                </div>
              ))}
            </div>
            <span style={{ fontSize: 11, color: "#8A8478" }}>From aggregate statistics only · {ai.source}. Save this version and open Analysis for the map, contact slicer, and density and top segments per area.</span>
          </>
        )}
      </section>

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
