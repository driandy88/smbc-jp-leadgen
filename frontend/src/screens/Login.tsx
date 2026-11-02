import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { HexMap, Outline } from "../components/HexMap";
import { Arrow, Logo } from "../components/Icons";

// Umeda and Namba at res 8, plus their rings, pulse over the real ward map
const PULSE = ["882e610503fffff", "882e61050bfffff", "882e610507fffff", "882e61056bfffff", "882e610569fffff", "882e61042dfffff"];

export function Login({ onLogin }: { onLogin: (token: string, initials: string) => void }) {
  const [email, setEmail] = useState("daniel.riandy@artefact.com");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [outline, setOutline] = useState<Outline | null>(null);

  useEffect(() => {
    fetch("/api/public/outline").then((r) => (r.ok ? r.json() : null)).then(setOutline).catch(() => {});
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const r = await api<{ token: string; initials: string }>("/api/auth/login", { body: { email, password } });
      onLogin(r.token, r.initials);
    } catch (x) {
      setErr(x instanceof Error ? x.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexWrap: "wrap", background: "#F3F0E8", color: "#1E1E1C", fontFamily: "'Inter Tight', 'Helvetica Neue', Arial, sans-serif" }}>
      <section aria-label="Osaka ward map" style={{ flex: "999 1 560px", minWidth: 0, minHeight: 520, position: "relative", overflow: "hidden", borderRight: "1px solid #D8D3C7", background: "#EFEBE1" }}>
        <div className="hx-drift" style={{ position: "absolute", inset: "4% 2%" }}>
          <div className="hx-pulse-layer" style={{ height: "100%" }}>
            <HexMap outline={outline} labels labelPx={14} height={760} ariaLabel="Osaka City wards"
              layers={[{ cells: PULSE.slice(0, 2), fill: "#C8442B", opacity: 0.18, stroke: "#C8442B" }, { cells: PULSE.slice(2), fill: "#C8442B", opacity: 0.07, stroke: "#C8442B" }]} />
          </div>
        </div>
        <div className="m" style={{ position: "absolute", left: 40, bottom: 36, display: "flex", flexDirection: "column", gap: 6, fontSize: 11, color: "#5E5A52", letterSpacing: "0.04em" }}>
          <span>34.6937° N · 135.5023° E</span>
          <span>H3 res 8 · 0.74 km² per cell · Umeda / Namba</span>
        </div>
        <div className="serif" style={{ position: "absolute", left: 40, top: 36, fontSize: 15, fontStyle: "italic", color: "#5E5A52" }}>Osaka, Kita → Minami</div>
      </section>

      <section style={{ flex: "1 1 460px", maxWidth: 620, minWidth: 0, display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "40px 64px", boxSizing: "border-box", gap: 48 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Logo w={44} h={40} />
            <span style={{ fontWeight: 600, fontSize: 15, letterSpacing: "0.22em" }}>HEXLINE</span>
          </div>
          <span className="m" style={{ fontSize: 11, letterSpacing: "0.06em", padding: "4px 8px", border: "1px solid #C8442B", color: "#A8371F", borderRadius: 2 }}>POC · Internal</span>
        </div>

        <div className="hx-in" style={{ display: "flex", flexDirection: "column", gap: 40, maxWidth: 380, width: "100%" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <h1 className="serif" style={{ margin: 0, fontWeight: 400, fontSize: 44, lineHeight: 1.05, letterSpacing: "-0.01em" }}>Find the next<br />merchant, block<br />by block.</h1>
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: "#5E5A52" }}>Merchant prospecting for SMBC acquiring sales, on an H3 grid.</p>
          </div>
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <label className="field-lbl">Work email
              <input className="hx-field" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="field-lbl">Password
              <input className="hx-field" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
            </label>
            {err && <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>}
            <button type="submit" className="btn" disabled={busy || !password} style={{ justifyContent: "space-between", minHeight: 48, marginTop: 10 }}>
              <span>{busy ? "Signing in…" : "Sign in"}</span><Arrow />
            </button>
          </form>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8, fontSize: 11, color: "#5E5A52", borderTop: "1px solid #D8D3C7", paddingTop: 16 }}>
          <span>Prepared for SMBC · Confidential</span>
          <span className="m">build 0.5.0</span>
        </div>
      </section>
    </div>
  );
}
