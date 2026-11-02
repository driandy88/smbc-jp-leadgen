import { fmt } from "../../lib/format";

export type Brief = {
  headline: string;
  takeaway?: string;
  kpis?: { label: string; value: string; context: string }[];
  where?: { area: string; leads: number; why: string }[];
  who?: { segment: string; count: number; pitch: string }[];
  when?: { window: string; why: string };
  actions: string[];
  caveats: string[];
  source: string;
  bullets?: { k: string; t: string }[]; // analyses saved before the structured brief
};

const Head = ({ n, t }: { n: string; t: string }) => (
  <div style={{ display: "flex", alignItems: "baseline", gap: 8, paddingBottom: 10, borderBottom: "1px solid #1E1E1C" }}>
    <span className="m" style={{ fontSize: 10, color: "#C8442B" }}>{n}</span>
    <span className="lbl" style={{ color: "#1E1E1C" }}>{t}</span>
  </div>
);

export function AiBrief({ s, name }: { s: Brief; name: string }) {
  if (!s.kpis) {
    return (
      <div className="card" style={{ padding: 22, display: "flex", flexDirection: "column", gap: 10 }}>
        <span className="m ai-tag">AI SUMMARY</span>
        <span style={{ fontSize: 15 }}>{s.headline}</span>
        {s.bullets?.map((b, i) => <span key={i} style={{ fontSize: 13 }}><span className="m" style={{ color: "#C8442B", fontSize: 11 }}>{b.k} </span>{b.t}</span>)}
        <span style={{ fontSize: 12, color: "#A8371F" }}>This analysis was saved in the old format. Re-analyze for the full lead brief.</span>
      </div>
    );
  }
  const maxLeads = Math.max(1, ...(s.where || []).map((w) => w.leads));

  return (
    <section className="card brief" aria-label="AI lead-generation brief">
      <div className="brief-top">
        <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: "0 0 180px" }}>
          <span className="m ai-tag">AI LEAD BRIEF</span>
          <span className="m" style={{ fontSize: 11, color: "#5E5A52", wordBreak: "break-all" }}>{name}</span>
        </div>
        <div style={{ flex: "1 1 480px", display: "flex", flexDirection: "column", gap: 8 }}>
          <h2 className="serif" style={{ margin: 0, fontWeight: 400, fontSize: 30, lineHeight: 1.15, letterSpacing: "-0.01em" }}>{s.headline}</h2>
          {s.takeaway && <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55, color: "#3A3833", maxWidth: 760 }}>{s.takeaway}</p>}
        </div>
      </div>

      <div className="brief-kpis">
        {s.kpis.map((k, i) => (
          <div key={k.label} className="brief-kpi">
            <span className="m" style={{ fontSize: 30, letterSpacing: "-0.02em", color: i === 0 ? "#C8442B" : "#1E1E1C" }}>{k.value}</span>
            <span style={{ fontSize: 13, fontWeight: 500 }}>{k.label}</span>
            <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.45 }}>{k.context}</span>
          </div>
        ))}
      </div>

      <div className="brief-cols">
        <div className="brief-col">
          <Head n="01" t="Where to send reps" />
          {(s.where || []).map((w, i) => (
            <div key={w.area} style={{ display: "flex", flexDirection: "column", gap: 5, padding: "12px 0", borderBottom: "1px solid #E2DDD1" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <span className="m" style={{ fontSize: 11, color: "#8A8478", width: 14 }}>{i + 1}</span>
                <span className="jp" style={{ fontSize: 16, fontWeight: 500 }}>{w.area}</span>
                <span className="m" style={{ marginLeft: "auto", fontSize: 15 }}>{fmt(w.leads)}</span>
                <span style={{ fontSize: 11, color: "#5E5A52" }}>leads</span>
              </div>
              <div style={{ marginLeft: 24, height: 4, background: "#E2DDD1" }}>
                <div style={{ height: 4, width: `${(100 * w.leads) / maxLeads}%`, background: i === 0 ? "#C8442B" : "#1E1E1C" }} />
              </div>
              <span style={{ marginLeft: 24, fontSize: 12, color: "#5E5A52", lineHeight: 1.45 }}>{w.why}</span>
            </div>
          ))}
        </div>

        <div className="brief-col">
          <Head n="02" t="Who to pitch" />
          {(s.who || []).map((w) => (
            <div key={w.segment} style={{ display: "flex", flexDirection: "column", gap: 6, padding: "12px 0", borderBottom: "1px solid #E2DDD1" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <span style={{ fontSize: 14, fontWeight: 500 }}>{w.segment}</span>
                <span className="m count-pill">{fmt(w.count)}</span>
              </div>
              <span style={{ fontSize: 13, lineHeight: 1.5, color: "#3A3833", borderLeft: "2px solid #C8442B", paddingLeft: 10 }}>{w.pitch}</span>
            </div>
          ))}
        </div>

        <div className="brief-col">
          <Head n="03" t="When to visit" />
          {s.when && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "12px 0" }}>
              <span className="serif" style={{ fontSize: 22 }}>{s.when.window}</span>
              <span style={{ fontSize: 13, lineHeight: 1.5, color: "#3A3833" }}>{s.when.why}</span>
            </div>
          )}
          <div style={{ marginTop: 8 }}><Head n="04" t="Watch-outs" /></div>
          <ul style={{ margin: 0, padding: "10px 0 0 16px", display: "flex", flexDirection: "column", gap: 6, fontSize: 12, lineHeight: 1.5, color: "#5E5A52" }}>
            {s.caveats.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
      </div>

      <div className="brief-actions">
        <span className="lbl" style={{ color: "#A39B88" }}>Next actions</span>
        <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(240px, 100%), 1fr))", gap: "10px 24px" }}>
          {s.actions.map((a, i) => (
            <li key={i} style={{ display: "flex", gap: 10, fontSize: 13, lineHeight: 1.5 }}>
              <span className="m" style={{ color: "#C8442B", fontSize: 12, paddingTop: 1 }}>{String(i + 1).padStart(2, "0")}</span>
              <span className="jp" style={{ fontFamily: "'Inter Tight', 'Noto Sans JP', sans-serif" }}>{a}</span>
            </li>
          ))}
        </ol>
      </div>

      <span style={{ fontSize: 11, color: "#8A8478" }}>Generated from aggregate statistics only · {s.source}. Payment data is self-reported on Google; check before sharing.</span>
    </section>
  );
}
