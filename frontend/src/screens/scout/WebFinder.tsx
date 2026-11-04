import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../../api";
import type { Points } from "../../components/PlaceMap";
import { fmt, pct } from "../../lib/format";
import { SheetButton } from "./Websites";
import { Profile } from "./types";

type Row = Record<string, any>;
type Find = { place_id: string; name: string; status: string; exists: boolean | null; website: string | null; site_type: string | null;
  social: string | null; confidence: string | null; reason: string | null; queries: string[] };
type Run = { id: number; status: string; error: string | null; total: number; done: number; errors: number; searching: number; found: number;
  workers: number; area: string | null; mock: boolean; cost_local: number; created_at: string; prompt_version: number; active?: string[]; recent?: Find[] };
type State = { remaining: number; remaining_callable: number; mock: boolean; per_merchant_local: number; currency: string;
  workers_max: number; limit_max: number; finds: Find[]; runs: Run[] };

const LIVE = ["queued", "running", "cancelling"];
const SECS_PER_MERCHANT = 15; // typical Gemini + Google Search round trip

/** The website-finder agent: searches the web for merchants whose listing has no website, N in parallel, and keeps what it finds. */
export function WebFinder({ p, points, versionId }: { p: Profile; points: Points | null; versionId: number }) {
  const [area, setArea] = useState("all");
  const [st, setSt] = useState<State | null>(null);
  const [limit, setLimit] = useState(25);
  const [workers, setWorkers] = useState(4);
  const [run, setRun] = useState<Run | null>(null);
  const [err, setErr] = useState("");
  const [show, setShow] = useState<"all" | "yes" | "no">("all");
  const [more, setMore] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  const [promptV, setPromptV] = useState<number | null>(null);
  useEffect(() => { api<{ version: number }>("/api/agent/prompt").then((x) => setPromptV(x.version)); }, []);
  const timer = useRef<number>();

  const areas: string[] = (p.areas || []).filter((a: Row) => a.selected ?? a.code !== "outside").map((a: Row) => a.en);
  const byId = useMemo(() => {
    const m = new Map<string, Row>();
    if (points) for (const r of points.rows) { const o = Object.fromEntries(points.cols.map((c, i) => [c, r[i]])) as Row; m.set(o.place_id, o); }
    return m;
  }, [points]);

  const load = () => api<State>(`/api/versions/${versionId}/websearch?area=${encodeURIComponent(area)}`).then((s) => {
    setSt(s);
    const live = s.runs.find((r) => LIVE.includes(r.status));
    if (live) setRun((cur) => cur?.id === live.id ? cur : live);
    return s;
  });
  useEffect(() => { load(); }, [versionId, area]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll a live run; reload the totals when it ends
  useEffect(() => {
    if (!run || !LIVE.includes(run.status)) return;
    let n = 0;
    const tick = async () => {
      try {
        const r = await api<Run>(`/api/websearch/${run.id}`);
        setRun(r);
        // The results table fills in as answers arrive, not only at the end
        if (++n % 4 === 0) load();
        if (LIVE.includes(r.status)) timer.current = window.setTimeout(tick, 1200);
        else load();
      } catch { timer.current = window.setTimeout(tick, 3000); }
    };
    timer.current = window.setTimeout(tick, 800);
    return () => window.clearTimeout(timer.current);
  }, [run?.id, run && LIVE.includes(run.status)]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    setErr("");
    try {
      setRun(await api<Run>(`/api/versions/${versionId}/websearch`, { body: { limit: Math.min(limit, st?.remaining || limit), workers, area } }));
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Couldn't start the agent"); }
  };
  const cancel = async () => { if (run) setRun({ ...run, ...(await api<Run>(`/api/websearch/${run.id}/cancel`, { method: "POST" })) }); };

  if (!st) return <span style={{ fontSize: 12, color: "#5E5A52" }}>Loading…</span>;
  const live = !!run && LIVE.includes(run.status);
  const n = Math.max(1, Math.min(limit, st.remaining));
  const cost = n * st.per_merchant_local;
  const mins = Math.max(1, Math.round((Math.ceil(n / workers) * SECS_PER_MERCHANT) / 60));
  const finds = st.finds.filter((f) => area === "all" || (byId.get(f.place_id)?.ward_en ?? byId.get(f.place_id)?.area_en) === area);
  const yes = finds.filter((f) => f.exists).length;
  const social = finds.filter((f) => f.social).length;
  const list = finds.filter((f) => show === "all" || (show === "yes") === !!f.exists);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, maxWidth: 940, color: "#1E1E1C" }}>
        An AI agent (Gemini with Google Search) takes each merchant whose Google Maps listing has no website, searches its name, phone and
        address, and decides whether a website that <b>really belongs to it</b> exists. Portals (Tabelog, Hot Pepper…) and social pages don't
        count; a social account it finds is kept in its own column. Merchants already answered are never searched twice. Call-list merchants go first.
      </p>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <button className="btn2" aria-expanded={showPrompt} onClick={() => setShowPrompt(!showPrompt)} style={{ minHeight: 0, padding: "6px 10px", fontSize: 12 }}>
          {showPrompt ? "Hide system prompt" : "View / edit system prompt"}
        </button>
        {promptV != null && <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>next run uses prompt v{promptV}{promptV === 0 ? " (default)" : ""}</span>}
      </div>
      {showPrompt && <PromptPanel onClose={() => setShowPrompt(false)} onSaved={setPromptV} />}

      {/* Parameters */}
      <div className="wf-params">
        <label className="wf-field">
          <span className="lbl">Area</span>
          <select className="in" value={area} onChange={(e) => setArea(e.target.value)} disabled={live}>
            <option value="all">All areas</option>
            {areas.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <span className="wf-hint">{fmt(st.remaining)} still to search · {fmt(st.remaining_callable)} on the call list</span>
        </label>
        <label className="wf-field">
          <span className="lbl">Merchants to search</span>
          <input className="in m" type="number" min={1} max={Math.max(1, Math.min(st.limit_max, st.remaining))} value={limit} disabled={live}
            onChange={(e) => setLimit(Math.max(1, Math.min(st.limit_max, Number(e.target.value) || 1)))} />
          <span style={{ display: "flex", gap: 6 }}>
            {[10, 25, 100, 500].map((x) => <button key={x} className="chip" aria-pressed={limit === x} disabled={live} onClick={(e) => { e.preventDefault(); setLimit(x); }}>{x}</button>)}
          </span>
        </label>
        <label className="wf-field">
          <span className="lbl">Agents in parallel · <span className="m">{workers}</span></span>
          <input type="range" min={1} max={st.workers_max} value={workers} disabled={live} onChange={(e) => setWorkers(Number(e.target.value))} />
          <span className="wf-hint">More agents finish sooner at the same cost</span>
        </label>
        <div className="wf-field" style={{ justifyContent: "flex-end" }}>
          <span className="wf-hint m">≈ {st.currency} {cost.toFixed(2)}{st.mock ? " (mock: free)" : ""} · ~{mins} min</span>
          {live
            ? <button className="btn2" onClick={cancel} disabled={run?.status === "cancelling"}>{run?.status === "cancelling" ? "Stopping…" : "Stop agent"}</button>
            : <button className="btn" onClick={start} disabled={!st.remaining}>Run agent on {fmt(n)} merchants</button>}
        </div>
      </div>
      {err && <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>}

      {run && (live || run.recent) && <LiveRun run={run} />}

      {/* What it has found so far */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12, borderTop: "1px solid #1E1E1C", paddingTop: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span className="lbl">Results · {area === "all" ? "all areas" : area}</span>
          <SheetButton path={`/api/versions/${versionId}/sheets/websearch`} label="Open results in Google Sheets" disabled={!st.finds.length} />
        </div>
        {finds.length ? (
          <>
            <div className="sum-mini" style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
              <Num v={fmt(finds.length)} l="merchants searched" />
              <Num v={fmt(yes)} l={`website found (${pct((100 * yes) / finds.length, 0)})`} red />
              <Num v={fmt(finds.length - yes)} l="no website of their own" />
              <Num v={fmt(social)} l="social account found" />
            </div>
            <div role="radiogroup" aria-label="Show" style={{ display: "flex", gap: 6 }}>
              {([["all", "All"], ["yes", "Website found"], ["no", "No website"]] as const).map(([k, l]) => (
                <button key={k} role="radio" className="chip" aria-checked={show === k} aria-pressed={show === k} onClick={() => setShow(k)}>{l}</button>
              ))}
            </div>
            <div style={{ overflowX: "auto" }}>
              <div style={{ minWidth: 860, fontSize: 12 }}>
                <div className="m wf-row" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
                  <span>MERCHANT</span><span>WEBSITE EXISTS</span><span>WEBSITE</span><span>CONFIDENCE</span><span>EVIDENCE</span><span>AREA · PHONE</span>
                </div>
                {list.slice(0, more ? 300 : 25).map((f) => {
                  const r = byId.get(f.place_id);
                  return (
                    <div key={f.place_id} className="wf-row" style={{ padding: "5px 0", borderBottom: "1px solid #E2DDD1" }}>
                      <a className="jp" href={r?.maps_uri || undefined} target="_blank" rel="noreferrer" style={{ textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</a>
                      <span style={{ color: f.exists ? "#1E1E1C" : "#A8371F", fontWeight: f.exists ? 600 : 400 }}>{f.exists ? "Yes" : "No"}</span>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {f.website ? <a href={f.website} target="_blank" rel="noreferrer">{f.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")} ↗</a> : ""}
                        {f.social && <a href={f.social} target="_blank" rel="noreferrer" style={{ marginLeft: f.website ? 8 : 0, color: "#3E5A63" }}>social ↗</a>}
                      </span>
                      <span className="m" style={{ color: "#5E5A52" }}>{f.confidence || "—"}</span>
                      <span title={f.queries.length ? `Searched: ${f.queries.join(" · ")}` : undefined} style={{ color: "#5E5A52", lineHeight: 1.35 }}>{f.reason}</span>
                      <span className="m" style={{ color: "#5E5A52", fontSize: 11 }}>{r ? `${r.ward_en ?? r.area_en ?? ""} · ${r.phone || "no phone"}` : ""}</span>
                    </div>
                  );
                })}
                {list.length > 25 && <button className="btn2" style={{ marginTop: 8 }} onClick={() => setMore(!more)}>{more ? "Show 25" : `Show more (${fmt(Math.min(300, list.length))})`}</button>}
              </div>
            </div>
          </>
        ) : <span style={{ fontSize: 12, color: "#5E5A52" }}>Nothing searched yet{area === "all" ? "" : ` in ${area}`}. Run the agent above; results appear here as it goes.</span>}
      </div>
    </div>
  );
}

const Num = ({ v, l, red }: { v: string; l: string; red?: boolean }) => (
  <span style={{ display: "flex", flexDirection: "column" }}>
    <span className="m" style={{ fontSize: 24, letterSpacing: "-0.02em", color: red ? "#C8442B" : undefined }}>{v}</span>
    <span style={{ fontSize: 11, color: "#5E5A52" }}>{l}</span>
  </span>
);

/** The run as it happens: one lane per agent with the merchant it is searching, a progress bar, and the latest answers. */
function LiveRun({ run }: { run: Run }) {
  const live = LIVE.includes(run.status);
  const lanes = Array.from({ length: Math.min(run.workers, Math.max(1, run.total - run.done + (run.active?.length || 0))) }, (_, i) => run.active?.[i]);
  const p = (100 * run.done) / Math.max(1, run.total);
  return (
    <div className="card wf-live" aria-live="polite">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "baseline" }}>
        <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
          {live && <span className="wf-dot" aria-hidden="true" />}
          <b>{live ? (run.status === "cancelling" ? "Stopping after the current searches…" : `${run.workers} agents searching`) : run.status === "done" ? "Done" : run.status === "cancelled" ? "Stopped" : "Failed"}</b>
          {run.mock && <span className="mock-tag">mock</span>}
          <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>prompt v{run.prompt_version ?? 0}</span>
        </span>
        <span className="m" style={{ fontSize: 12, color: "#5E5A52" }}>
          {fmt(run.done)} / {fmt(run.total)} · {fmt(run.found)} websites found{run.errors ? ` · ${run.errors} errors` : ""} · {run.cost_local.toFixed(2)} spent
        </span>
      </div>
      <div className="wf-bar"><span style={{ width: `${p}%` }} /></div>
      {run.error && <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{run.error}</span>}

      {live && (
        <div className="wf-lanes">
          {lanes.map((name, i) => (
            <div key={i} className="wf-lane" data-idle={!name}>
              <span className="m" style={{ color: "#8A8478", width: 18 }}>{i + 1}</span>
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className={name ? "wf-glass" : undefined}>
                <circle cx="6.5" cy="6.5" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M10 10l4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
              <span className="jp" style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name || "waiting…"}</span>
              {name && <span className="wf-scan" aria-hidden="true" />}
            </div>
          ))}
        </div>
      )}

      {!!run.recent?.length && (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {run.recent.slice(0, 6).map((f) => (
            <div key={f.place_id} className="wf-feed hx-in">
              <span className={f.exists ? "wf-yes" : "wf-no"} aria-hidden="true">{f.status === "error" ? "!" : f.exists ? "✓" : "–"}</span>
              <span className="jp" style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
              <span style={{ color: "#5E5A52", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {f.status === "error" ? "search failed" : f.website ? f.website.replace(/^https?:\/\/(www\.)?/, "") : "no website of its own"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

type PromptVersion = { version: number; text: string; note: string; author: string; created_at: string };
type PromptState = { version: number; text: string; default: string; output_rules: string; versions: PromptVersion[] };

/** The agent's system prompt: read it, edit it, save each edit as a new version, load any older one back. */
export function PromptPanel({ onClose, onSaved }: { onClose: () => void; onSaved: (v: number) => void }) {
  const [st, setSt] = useState<PromptState | null>(null);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [from, setFrom] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const load = () => api<PromptState>("/api/agent/prompt").then((s) => { setSt(s); setText(s.text); setFrom(`v${s.version}`); });
  useEffect(() => { load(); }, []);

  if (!st) return <div className="card wf-prompt"><span style={{ fontSize: 12, color: "#5E5A52" }}>Loading prompt…</span></div>;
  const dirty = text.trim() !== st.text.trim();
  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const p = await api<PromptVersion>("/api/agent/prompt", { body: { text, note } });
      setNote("");
      await load();
      onSaved(p.version);
      setMsg({ ok: true, t: `Saved as v${p.version}. New runs use it from now on.` });
    } catch (e) { setMsg({ ok: false, t: e instanceof ApiError ? e.message : "Couldn't save" }); } finally { setBusy(false); }
  };
  const pick = (t: string, label: string) => { setText(t); setFrom(label); setMsg(null); };
  const when = (s: string) => new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

  return (
    <div className="card wf-prompt">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <span style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
          <span className="lbl">Agent system prompt</span>
          <span className="m" style={{ fontSize: 12 }}>in use: v{st.version}{st.version === 0 ? " (built-in default)" : ""}</span>
          {from !== `v${st.version}` && <span className="m" style={{ fontSize: 11, color: "#C8442B" }}>editing from {from}</span>}
        </span>
        <button className="btn2" onClick={onClose} style={{ minHeight: 0, padding: "4px 10px", fontSize: 12 }}>Close</button>
      </div>
      <div className="wf-prompt-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
          <textarea className="wf-prompt-text m" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} aria-label="System prompt" />
          <details>
            <summary style={{ fontSize: 12, color: "#5E5A52", cursor: "pointer" }}>Fixed output format (appended to every version, not editable: the app reads this JSON)</summary>
            <pre className="wf-prompt-fixed m">{st.output_rules}</pre>
          </details>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input className="in" placeholder="What changed? e.g. stricter on namesakes" value={note} onChange={(e) => setNote(e.target.value)} style={{ flex: "1 1 240px", fontSize: 13 }} maxLength={300} />
            <button className="btn2" disabled={!dirty || busy} onClick={() => pick(st.text, `v${st.version}`)}>Discard changes</button>
            <button className="btn" disabled={!dirty || busy} onClick={save}>{busy ? "Saving…" : `Save as v${(st.versions[0]?.version ?? 0) + 1}`}</button>
          </div>
          {msg && <span role={msg.ok ? "status" : "alert"} style={{ fontSize: 12, color: msg.ok ? "#5E7D4A" : "#B33A3A" }}>{msg.t}</span>}
          <span style={{ fontSize: 11, color: "#5E5A52" }}>A run keeps the version it started with; the results sheet shows which version answered each merchant.</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 0, minWidth: 0 }}>
          <span className="lbl" style={{ marginBottom: 6 }}>Versions</span>
          <div style={{ maxHeight: 420, overflow: "auto" }}>
            {st.versions.map((p) => (
              <div key={p.version} className="wf-ver" data-on={p.version === st.version}>
                <span className="m" style={{ fontWeight: 600 }}>v{p.version}</span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.note || <span style={{ color: "#8A8478" }}>no note</span>}</span>
                  <span className="m" style={{ fontSize: 10, color: "#8A8478" }}>{when(p.created_at)} · {p.author.split("@")[0]}{p.version === st.version ? " · in use" : ""}</span>
                </span>
                <button className="chip" onClick={() => pick(p.text, `v${p.version}`)}>Load</button>
              </div>
            ))}
            <div className="wf-ver" data-on={st.version === 0}>
              <span className="m" style={{ fontWeight: 600 }}>v0</span>
              <span><span style={{ display: "block" }}>Built-in default</span><span className="m" style={{ fontSize: 10, color: "#8A8478" }}>ships with the app{st.version === 0 ? " · in use" : ""}</span></span>
              <button className="chip" onClick={() => pick(st.default, "v0")}>Load</button>
            </div>
          </div>
          <span style={{ fontSize: 11, color: "#5E5A52", marginTop: 6 }}>Load an older version, then save it to make it the one in use again.</span>
        </div>
      </div>
    </div>
  );
}
