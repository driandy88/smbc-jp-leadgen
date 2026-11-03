import { getResolution } from "h3-js";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { HexMap, Outline } from "../../components/HexMap";
import { Done, Squiggle } from "../../components/Icons";
import { elapsed, fmt, timeOf, utc, money } from "../../lib/format";
import { Run } from "./types";

type Cell = { h: string; s: "queued" | "active" | "done"; n: number; sat: boolean };

const LIVE = ["queued", "running", "cancelling"];

export function Running({ runId, onFilter, onBack, onUpdate }: { runId: number; onFilter: () => void; onBack: () => void; onUpdate: (r: Run) => void }) {
  const [run, setRun] = useState<Run | null>(null);
  const [cells, setCells] = useState<Cell[]>([]);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [, tick] = useState(0);

  useEffect(() => {
    let stop = false;
    let n = 0;
    const poll = async () => {
      const r = await api<Run>(`/api/runs/${runId}`).catch(() => null);
      if (stop || !r) return;
      setRun(r);
      if (!LIVE.includes(r.status)) onUpdate(r);
      if (n++ % 2 === 0 || !LIVE.includes(r.status)) api<Cell[]>(`/api/runs/${runId}/cells`).then((c) => !stop && setCells(c));
      if (LIVE.includes(r.status)) setTimeout(poll, 1000);
    };
    poll();
    const t = setInterval(() => tick((x) => x + 1), 1000);
    return () => { stop = true; clearInterval(t); };
  }, [runId]);

  useEffect(() => {
    if (run && !outline) api<Outline>("/api/scout/geometry", { body: run.areas.map((a) => a.area) }).then(setOutline);
  }, [run, outline]);

  // Only base-resolution cells on the map; split children are summarised in the stats
  const layers = useMemo(() => {
    if (!run) return [];
    const base = cells.filter((c) => getResolution(c.h) === run.base_res);
    return [
      { cells: base.filter((c) => c.s === "queued").map((c) => c.h), fill: "none", stroke: "#C9C2B2" },
      { cells: base.filter((c) => c.s === "done").map((c) => c.h), fill: "#1E1E1C", opacity: 0.82 },
      { cells: base.filter((c) => c.s === "done" && c.sat).map((c) => c.h), fill: "#8F2D1B", opacity: 0.9 },
      { cells: cells.filter((c) => c.s === "active").map((c) => c.h), fill: "#C8442B" },
    ];
  }, [cells, run]);

  if (!run) return null;
  const live = LIVE.includes(run.status);
  const done = run.status === "done";
  const title = { queued: "Starting…", running: "Retrieving places", cancelling: "Cancelling…", cancelled: "Run cancelled", done: "Retrieval complete", failed: "Run failed" }[run.status] || run.status;
  const stats = [
    { l: "Elapsed", v: elapsed(utc(run.created_at), run.finished_at ? utc(run.finished_at) : null) },
    { l: "API calls", v: fmt(run.api_calls) },
    { l: "Raw hits", v: fmt(run.raw_hits) },
    { l: "Unique", v: fmt(run.unique_places) },
    { l: "Dupes merged", v: fmt(run.dupes) },
    { l: "Splits / saturated", v: `${fmt(run.splits)} / ${fmt(run.saturated)}` },
    { l: run.mock ? "Spent (simulated)" : "Spent", v: money(run.cost_local) },
  ];
  const pctDone = run.total_tasks ? (100 * run.done_tasks) / run.total_tasks : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div className="card" style={{ padding: "20px 22px", display: "flex", flexWrap: "wrap", gap: "20px 40px", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flex: "1 1 320px" }}>
          {done ? <Done /> : live ? <Squiggle /> : null}
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <span style={{ fontSize: 17, fontWeight: 500 }}>{title}{run.mock && <span className="m mock-tag">MOCK</span>}</span>
            <span className="m" style={{ fontSize: 12, color: "#5E5A52" }}>run {run.id} · {run.keywords.length} keywords · {run.areas.length} areas · res {run.base_res} → {run.max_res} split</span>
            {run.error && <span style={{ fontSize: 12, color: "#B33A3A" }}>{run.error}</span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
          {stats.map((s) => <div key={s.l} style={{ display: "flex", flexDirection: "column", gap: 2 }}><span className="lbl">{s.l}</span><span className="m" style={{ fontSize: 20 }}>{s.v}</span></div>)}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {live && <button className="btn2" disabled={run.status === "cancelling"} onClick={() => api(`/api/runs/${runId}/cancel`, { method: "POST" })}>Cancel</button>}
          {!live && <button className="btn2" onClick={onBack}>← New search</button>}
          {done && <button className="btn" onClick={onFilter}>Continue to Filter →</button>}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: 14, fontWeight: 500 }}>All areas</span>
          <span className="m" style={{ fontSize: 12, color: "#5E5A52" }}>{fmt(run.done_tasks)} / {fmt(run.total_tasks)} searches · {pctDone.toFixed(0)}%{run.estimate ? ` · estimate ${fmt(run.estimate.expected_calls)} calls` : ""}</span>
        </div>
        <div style={{ height: 3, background: "#E2DDD1" }}><div style={{ height: 3, background: "#1E1E1C", width: `${pctDone}%`, transition: "width .3s linear" }} /></div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 24, alignItems: "flex-start" }}>
        <div style={{ flex: "999 1 520px", minWidth: 0, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(240px, 100%), 1fr))", gap: "14px 20px", alignContent: "start" }}>
          {(run.area_progress || []).map((a) => {
            const p = a.total ? (100 * a.done) / a.total : 0;
            return (
              <div key={a.area} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
                  <span style={{ fontSize: 13 }}>{a.en} <span className="jp" style={{ color: "#5E5A52", fontSize: 12 }}>{a.jp}</span></span>
                  <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{fmt(a.done)} / {fmt(a.total)}</span>
                </div>
                <div style={{ height: 3, background: "#E2DDD1" }}><div style={{ height: 3, background: p >= 100 ? "#1E1E1C" : "#C8442B", width: `${p}%`, transition: "width .3s linear" }} /></div>
              </div>
            );
          })}
        </div>

        <div style={{ flex: "1 1 360px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span className="lbl">Cells · res {run.base_res}</span>
              <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{fmt(cells.filter((c) => c.s === "done").length)} / {fmt(cells.length)} incl. splits</span>
            </div>
            <HexMap outline={outline} layers={layers} height={300} labels={false} ariaLabel="Hex cells completed" />
            <div style={{ display: "flex", gap: 14, fontSize: 11, color: "#5E5A52", flexWrap: "wrap" }}>
              <span className="legend"><span style={{ background: "#1E1E1C" }} />done</span>
              <span className="legend"><span style={{ background: "#C8442B" }} />querying</span>
              <span className="legend"><span style={{ background: "#8F2D1B" }} />saturated</span>
              <span className="legend"><span style={{ border: "1px solid #C9C2B2" }} />queued</span>
            </div>
          </div>
          <div className="log">
            <span className="lbl" style={{ color: "#A39B88" }}>Log</span>
            {(run.logs || []).map((l, i) => (
              <span key={i} className="m" style={{ fontSize: 11, lineHeight: 1.5, color: l.level === "error" ? "#F08A75" : l.level === "warn" ? "#E8C07A" : undefined, opacity: i < (run.logs!.length - 6) ? 0.55 : 1 }}>
                <span style={{ color: "#A39B88" }}>{timeOf(l.t)} </span><span className="jp">{l.m}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
