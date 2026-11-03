import { useEffect, useState } from "react";
import { api } from "../../api";
import { setCurrency } from "../../lib/format";
import { Analysis } from "./Analysis";
import { Define } from "./Define";
import { Filter } from "./Filter";
import { Result } from "./Result";
import { Running } from "./Running";
import { Filters, Run, ScoutConfig } from "./types";

export type Stage = "define" | "running" | "filter" | "result" | "analysis";

const STEPS: [string, string, Stage][] = [["01", "Retrieve", "define"], ["02", "Filter", "filter"], ["03", "Summary", "result"], ["04", "Versions", "analysis"]];

export function Scout({ onDataChip }: { onDataChip: (s: string) => void }) {
  const [cfg, setCfg] = useState<ScoutConfig | null>(null);
  const [stage, setStage] = useState<Stage>("define");
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [filters, setFilters] = useState<Partial<Filters>>({});

  useEffect(() => {
    api<ScoutConfig>("/api/scout/config").then((c) => { setCurrency(c.currency); setCfg(c); });
    // Resume an unfinished run, or offer the latest finished one for filtering
    api<Run[]>("/api/runs").then((runs) => {
      const live = runs.find((r) => ["queued", "running", "cancelling"].includes(r.status));
      if (live) {
        setRunId(live.id);
        setStage("running");
      } else {
        const done = runs.find((r) => r.status === "done");
        if (done) {
          setRunId(done.id);
          setRun(done);
        }
      }
    });
  }, []);

  useEffect(() => {
    if (runId) api<Run>(`/api/runs/${runId}`).then(setRun);
  }, [runId, stage]);

  const runDone = run?.status === "done";
  const stIdx = { define: 0, running: 0, filter: 1, result: 2, analysis: 3 }[stage];
  const canGo = (s: Stage) => s === "define" || s === "analysis" || runDone;

  const openRun = (id: number, to: Stage) => {
    setRunId(id);
    setFilters({});
    setStage(to);
  };

  return (
    <main style={{ padding: "28px 40px 64px", boxSizing: "border-box", width: "100%", maxWidth: 1360, display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-end", gap: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="m" style={{ fontSize: 11, color: "#C8442B" }}>01 — SCOUT{run && stage !== "define" ? ` · RUN ${run.id}${run.mock ? " · MOCK" : ""}` : ""}</span>
          <h1 className="serif" style={{ margin: 0, fontWeight: 400, fontSize: 36, letterSpacing: "-0.01em" }}>Gather places</h1>
        </div>
        <div role="list" aria-label="Scout steps" style={{ display: "flex", alignItems: "flex-start" }}>
          {STEPS.map(([k, label, s], i) => (
            <div role="listitem" key={k} style={{ display: "flex", alignItems: "flex-start" }}>
              <button onClick={() => canGo(s) && setStage(s === "define" && stage === "running" ? "running" : s)} disabled={!canGo(s)} aria-current={i === stIdx ? "step" : undefined}
                style={{ font: "inherit", background: "transparent", border: "none", cursor: canGo(s) ? "pointer" : "default", display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: "0 4px", minWidth: 92, color: "#1E1E1C", opacity: canGo(s) ? 1 : 0.55 }}>
                <span style={{ width: 12, height: 12, borderRadius: "50%", boxSizing: "border-box", ...(i === stIdx ? { background: "#C8442B", border: "1.5px solid #C8442B" } : i < stIdx ? { background: "#1E1E1C", border: "1.5px solid #1E1E1C" } : { background: "#F3F0E8", border: "1.5px solid #9C9586" }) }} />
                <span style={{ fontSize: 12, ...(i === stIdx ? { fontWeight: 600 } : { color: "#5E5A52" }) }}><span className="m" style={{ fontSize: 10, marginRight: 4 }}>{k}</span>{label}</span>
              </button>
              {i < STEPS.length - 1 && <span aria-hidden="true" style={{ width: 44, height: 1, marginTop: 6, background: i < stIdx ? "#1E1E1C" : "#BDB6A7" }} />}
            </div>
          ))}
        </div>
      </div>

      {!cfg ? null : stage === "define" ? (
        <Define cfg={cfg} lastRun={run} onStarted={(id) => openRun(id, "running")} onOpenRun={(id) => openRun(id, "filter")} />
      ) : stage === "running" && runId ? (
        <Running runId={runId} onFilter={() => setStage("filter")} onBack={() => setStage("define")} onUpdate={setRun} />
      ) : stage === "filter" && runId ? (
        <Filter runId={runId} filters={filters} setFilters={setFilters} onBack={() => setStage("define")} onNext={() => setStage("result")} />
      ) : stage === "result" && runId ? (
        <Result runId={runId} filters={filters} onSaved={(name) => onDataChip(name)} onNext={() => setStage("analysis")} onBack={() => setStage("filter")} />
      ) : stage === "analysis" ? (
        <Analysis onDataChip={onDataChip} />
      ) : null}
    </main>
  );
}
