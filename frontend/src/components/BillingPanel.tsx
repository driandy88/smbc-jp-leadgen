import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, session } from "../api";
import { fmt, timeOf, shortDate, money } from "../lib/format";
import { Close, Lock } from "./Icons";

type Bucket = { calls: number; usd: number; local: number };
type Summary = {
  budget: number; usd_rate: number; currency: string; month: string; errors: number;
  real_month: Bucket; mock_month: Bucket; real_total: Bucket; mock_total: Bucket;
  by_sku: { api: string; sku: string; mock: boolean; calls: number; usd: number; local: number; avg_ms: number }[];
  by_run: { run_id: number | null; mock: boolean; calls: number; usd: number; local: number }[];
  by_day: { day: string; mock: boolean; calls: number; local: number }[];
  pricing: { places_usd_per_1000: number; field_mask: string; llm_model: string; llm_usd_per_mtok: number[] };
};
type Call = {
  id: number; ts: string; run_id: number | null; version_id: number | null; api: string; sku: string; mock: boolean;
  status: string; ms: number; usd: number; local: number; hex: string | null; res: number | null; keyword: string | null;
  page: number | null; results: number | null; tokens_in: number | null; tokens_out: number | null;
};

const PAGE = 50;

export function BillingPanel({ onClose }: { onClose: () => void }) {
  const [unlocked, setUnlocked] = useState(!!session.billing);
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [sum, setSum] = useState<Summary | null>(null);
  const [calls, setCalls] = useState<{ total: number; rows: Call[] } | null>(null);
  const [filter, setFilter] = useState<{ api: string; mock: string; run: string }>({ api: "", mock: "", run: "" });
  const [page, setPage] = useState(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const relock = (e: unknown) => {
    if (e instanceof ApiError && e.status === 403) {
      session.setBilling("");
      setUnlocked(false);
    }
  };

  useEffect(() => {
    if (!unlocked) return;
    api<Summary>("/api/billing/summary", { billing: true }).then(setSum).catch(relock);
  }, [unlocked]);

  useEffect(() => {
    if (!unlocked) return;
    const q = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
    if (filter.api) q.set("api", filter.api);
    if (filter.mock) q.set("mock", filter.mock);
    if (filter.run) q.set("run_id", filter.run);
    api<{ total: number; rows: Call[] }>(`/api/billing/calls?${q}`, { billing: true }).then(setCalls).catch(relock);
  }, [unlocked, filter, page]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    try {
      const r = await api<{ token: string }>("/api/billing/unlock", { body: { passcode: code } });
      session.setBilling(r.token);
      setUnlocked(true);
    } catch (x) {
      setErr(x instanceof Error ? x.message : "Failed");
    }
  };

  return (
    <div role="dialog" aria-modal="true" aria-label="Billing" style={{ position: "fixed", inset: 0, background: "rgba(30,30,28,0.35)", zIndex: 50, display: "flex", justifyContent: "flex-end" }} onClick={onClose}>
      <div className="billing-panel" onClick={(e) => e.stopPropagation()} style={{ width: "min(980px, 100%)", height: "100%", overflowY: "auto", background: "#F3F0E8", borderLeft: "1px solid #1E1E1C", padding: "24px 28px 48px", boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="m" style={{ fontSize: 11, color: "#C8442B" }}>CONFIG · BILLING</span>
            <h2 className="serif" style={{ margin: 0, fontWeight: 400, fontSize: 26 }}>API spend ledger</h2>
          </div>
          <button className="btn2" onClick={onClose} aria-label="Close billing"><Close color="#1E1E1C" /> Close</button>
        </div>

        {!unlocked ? (
          <form onSubmit={submit} className="card" style={{ padding: 24, display: "flex", flexDirection: "column", gap: 14, maxWidth: 380 }}>
            <span style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 14 }}><Lock /> Enter the passcode to view billing.</span>
            <input className="in m" type="password" autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder="Passcode" aria-label="Billing passcode" />
            {err && <span style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>}
            <button className="btn" type="submit" disabled={!code}>Unlock</button>
          </form>
        ) : (
          <>
            {sum && (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", borderTop: "1px solid #1E1E1C", borderBottom: "1px solid #D8D3C7" }}>
                  {[
                    { v: money(sum.real_month.local), l: `Real spend · ${sum.month}`, s: `${fmt(sum.real_month.calls)} calls · $${sum.real_month.usd.toFixed(2)} · budget ${money(sum.budget)}` },
                    { v: money(sum.real_total.local), l: "Real spend · all time", s: `${fmt(sum.real_total.calls)} calls · $${sum.real_total.usd.toFixed(2)}` },
                    { v: fmt(sum.mock_total.calls), l: "Mock calls (not billed)", s: `would have cost ${money(sum.mock_total.local)}` },
                    { v: fmt(sum.errors), l: "Calls with errors", s: "non-OK status, all time" },
                  ].map((s) => (
                    <div key={s.l} style={{ padding: "16px 14px", display: "flex", flexDirection: "column", gap: 4, borderRight: "1px solid #E2DDD1" }}>
                      <span className="m" style={{ fontSize: 26 }}>{s.v}</span>
                      <span style={{ fontSize: 13 }}>{s.l}</span>
                      <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{s.s}</span>
                    </div>
                  ))}
                </div>

                <Table title="By SKU" head={["API", "SKU", "MODE", "CALLS", "AVG MS", "USD", "JPY"]} cols="1fr 1.6fr 70px 80px 70px 80px 90px"
                  rows={sum.by_sku.map((r) => [r.api, r.sku, r.mock ? "mock" : "real", fmt(r.calls), fmt(r.avg_ms), `$${r.usd.toFixed(2)}`, money(r.local)])} />
                <Table title="By run" head={["RUN", "MODE", "CALLS", "USD", "JPY"]} cols="1fr 80px 90px 90px 100px"
                  rows={sum.by_run.map((r) => [r.run_id == null ? "—" : `run ${r.run_id}`, r.mock ? "mock" : "real", fmt(r.calls), `$${r.usd.toFixed(2)}`, money(r.local)])}
                  onRow={(i) => { const r = sum.by_run[i]; if (r.run_id != null) { setFilter({ ...filter, run: String(r.run_id) }); setPage(0); } }} />
                <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>
                  Rates: Places ${sum.pricing.places_usd_per_1000}/1k calls (field mask "{sum.pricing.field_mask}") · {sum.pricing.llm_model} ${sum.pricing.llm_usd_per_mtok[0]}/${sum.pricing.llm_usd_per_mtok[1]} per MTok · {sum.currency} {sum.usd_rate}/USD. List prices; Google's monthly free tier is not deducted.
                </span>
              </>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                <span className="lbl" style={{ marginRight: "auto" }}>Every call · {fmt(calls?.total)}</span>
                <select className="in" value={filter.api} onChange={(e) => { setFilter({ ...filter, api: e.target.value }); setPage(0); }} aria-label="API">
                  <option value="">All APIs</option><option value="places.searchText">Places Text Search</option><option value="vertex.gemini">Vertex Gemini</option><option value="vertex.claude">Vertex Claude</option>
                </select>
                <select className="in" value={filter.mock} onChange={(e) => { setFilter({ ...filter, mock: e.target.value }); setPage(0); }} aria-label="Mode">
                  <option value="">Real + mock</option><option value="false">Real only</option><option value="true">Mock only</option>
                </select>
                {filter.run && <button className="btn2" onClick={() => setFilter({ ...filter, run: "" })}>run {filter.run} <Close color="#1E1E1C" /></button>}
              </div>
              <Table head={["TIME (JST)", "RUN", "API", "MODE", "HEX / RES", "KEYWORD", "PG", "RESULTS", "MS", "STATUS", "JPY"]}
                cols="130px 50px 120px 50px 150px 1fr 30px 60px 50px 70px 60px"
                rows={(calls?.rows || []).map((c) => [
                  `${shortDate(c.ts).slice(5)} ${timeOf(c.ts)}`, c.run_id ?? "—", c.api, c.mock ? "mock" : "real",
                  c.hex ? `${c.hex} · ${c.res}` : c.tokens_in != null ? `${fmt(c.tokens_in)}→${fmt(c.tokens_out)} tok` : "—",
                  c.keyword ?? "—", c.page ?? "", c.results ?? "", c.ms, c.status, c.mock ? `(${c.local.toFixed(1)})` : c.local.toFixed(1),
                ])} />
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", alignItems: "center" }}>
                <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{page * PAGE + 1}–{Math.min((page + 1) * PAGE, calls?.total || 0)}</span>
                <button className="btn2" disabled={page === 0} onClick={() => setPage(page - 1)}>Newer</button>
                <button className="btn2" disabled={!calls || (page + 1) * PAGE >= calls.total} onClick={() => setPage(page + 1)}>Older</button>
                <button className="btn2" onClick={() => { session.setBilling(""); setUnlocked(false); setSum(null); setCalls(null); }}><Lock /> Lock</button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Table({ title, head, rows, cols, onRow }: { title?: string; head: string[]; rows: (string | number)[][]; cols: string; onRow?: (i: number) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", overflowX: "auto" }}>
      {title && <span className="lbl" style={{ paddingBottom: 8 }}>{title}</span>}
      <div style={{ minWidth: 640 }}>
        <div className="m" style={{ display: "grid", gridTemplateColumns: cols, gap: 8, fontSize: 10, color: "#5E5A52", letterSpacing: "0.05em", padding: "6px 0", borderBottom: "1px solid #1E1E1C" }}>
          {head.map((h) => <span key={h}>{h}</span>)}
        </div>
        {rows.length === 0 && <div style={{ padding: "12px 0", fontSize: 12, color: "#8A8478" }}>Nothing recorded yet.</div>}
        {rows.map((r, i) => (
          <div key={i} className="m" onClick={onRow ? () => onRow(i) : undefined} style={{ display: "grid", gridTemplateColumns: cols, gap: 8, fontSize: 11, padding: "7px 0", borderBottom: "1px solid #E2DDD1", cursor: onRow ? "pointer" : undefined, alignItems: "center" }}>
            {r.map((c, j) => <span key={j} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} className={j === 5 ? "jp" : undefined}>{c}</span>)}
          </div>
        ))}
      </div>
    </div>
  );
}
