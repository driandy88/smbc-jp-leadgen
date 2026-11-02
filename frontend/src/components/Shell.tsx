import { ReactNode, useEffect, useState } from "react";
import { api } from "../api";
import { money, setCurrency } from "../lib/format";
import { BillingPanel } from "./BillingPanel";
import { Lock, Logo } from "./Icons";

export type Route = "scout" | "score" | "field";

const NAV: { k: Route; n: string; label: string; icon: ReactNode }[] = [
  { k: "scout", n: "01", label: "Scout", icon: <path d="M10.2 3.6 Q13.4 5.4 16.4 7.2 Q16.6 10.6 16.3 14 Q13.3 15.8 10.1 17.4 Q7 15.7 3.9 14 Q3.7 10.5 4 7.2 Q7.1 5.3 10.2 3.6 Z M15.4 15.8 Q18 18.3 20.6 20.9" fill="none" stroke="#1E1E1C" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /> },
  { k: "score", n: "02", label: "Score", icon: <path d="M3.6 3.8 Q3.3 12 3.6 20.4 Q12 20.7 20.6 20.3 M6.6 16.8 Q9.6 16 11.4 12.6 Q13.3 9.1 17.4 7.6" fill="none" stroke="#1E1E1C" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /> },
  { k: "field", n: "03", label: "Field", icon: <path d="M8.7 7.2 Q8.3 10.4 8.6 13.1 Q7.3 16.6 5.8 20.6 M8.6 13.1 Q10.4 16.3 11.8 20.4 M5.6 10.6 Q8.6 8.4 11.8 10.4 M16.6 20.6 Q16.4 15 16.5 9.4 Q18.7 9.1 20.7 10.4 Q18.5 11.6 16.5 12.6" fill="none" stroke="#1E1E1C" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /> },
];

type Meter = { month: string; spent_local: number; budget: number; currency: string };

export function Shell({ route, onNav, onLogout, initials, dataChip, children }: {
  route: Route; onNav: (r: Route) => void; onLogout: () => void; initials: string; dataChip: string; children: ReactNode;
}) {
  const [meter, setMeter] = useState<Meter | null>(null);
  const [billing, setBilling] = useState(false);

  useEffect(() => {
    const load = () => api<Meter>("/api/billing/meter").then((m) => { setCurrency(m.currency); setMeter(m); }).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const share = meter ? Math.min(100, (100 * meter.spent_local) / Math.max(1, meter.budget)) : 0;
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexWrap: "wrap", background: "#F3F0E8", color: "#1E1E1C", fontFamily: "'Inter Tight', 'Helvetica Neue', Arial, sans-serif" }}>
      <nav aria-label="Primary" style={{ flex: "1 1 88px", minWidth: 88, borderRight: "1px solid #D8D3C7", display: "flex", flexDirection: "column", alignItems: "center", gap: 32, padding: "16px 0 20px", boxSizing: "border-box" }}>
        <button type="button" onClick={onLogout} aria-label="Hexline — sign out" title="Sign out" style={{ font: "inherit", background: "transparent", border: "none", cursor: "pointer", display: "flex", padding: 6 }}>
          <Logo />
        </button>
        <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: 26, alignItems: "center" }}>
          <span aria-hidden="true" style={{ position: "absolute", top: 30, bottom: 40, left: "50%", width: 1, background: "#1E1E1C", opacity: 0.3 }} />
          {NAV.map((n) => {
            const on = n.k === route;
            return (
              <button key={n.k} type="button" onClick={() => onNav(n.k)} aria-current={on ? "page" : undefined} style={{ font: "inherit", background: "transparent", border: "none", cursor: "pointer", padding: 0, position: "relative", display: "flex", flexDirection: "column", alignItems: "center", gap: 5, color: on ? "#1E1E1C" : "#5E5A52", minWidth: 64 }}>
                <span className="m" style={{ fontSize: 10, color: on ? "#C8442B" : undefined, background: "#F3F0E8", padding: "0 4px" }}>{n.n}</span>
                <span style={{ width: 40, height: 40, borderRadius: "50%", border: on ? "1.5px solid #C8442B" : "1px solid #BDB6A7", background: "#F3F0E8", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">{n.icon}{n.k === "scout" && <circle cx="10.2" cy="10.5" r="1.4" fill="#C8442B" />}</svg>
                </span>
                <span style={{ fontSize: 12, fontWeight: on ? 600 : 400, background: "#F3F0E8", padding: "0 4px" }}>{n.label}</span>
              </button>
            );
          })}
        </div>
      </nav>

      <div style={{ flex: "999 1 560px", minWidth: 0, display: "flex", flexDirection: "column" }}>
        <header style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "12px 24px", padding: "12px 32px", minHeight: 60, boxSizing: "border-box", borderBottom: "1px solid #D8D3C7" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <span className="serif" style={{ fontSize: 19 }}>Osaka FnB Pilot</span>
            <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>PRJ-0142</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <span className="m chip-static"><span style={{ width: 6, height: 6, background: "#1E1E1C" }} />data {dataChip || "—"}</span>
            <span className="m chip-static"><span style={{ width: 6, height: 6, borderRadius: "50%", background: "#5E7D4A" }} />model prospect-lgbm v3 · prod</span>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 190 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <span className="lbl">Maps API · {meter?.month || "—"}</span>
                <span className="m" style={{ fontSize: 12 }}>{money(meter?.spent_local)} <span style={{ color: "#5E5A52" }}>/ {money(meter?.budget)}</span></span>
              </div>
              <div style={{ height: 2, background: "#D8D3C7" }}><div style={{ height: 2, width: `${share}%`, background: share > 85 ? "#C8442B" : "#1E1E1C" }} /></div>
            </div>
            <button type="button" className="iconbtn" onClick={() => setBilling(true)} aria-label="Billing details (locked)" title="Billing details">
              <Lock />
            </button>
            <button type="button" onClick={onLogout} title="Sign out" aria-label={`Account ${initials}, sign out`} style={{ width: 36, height: 36, borderRadius: "50%", border: "1px solid #1E1E1C", background: "#EAE5D9", font: "inherit", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>{initials}</button>
          </div>
        </header>
        {children}
      </div>
      {billing && <BillingPanel onClose={() => setBilling(false)} />}
    </div>
  );
}
