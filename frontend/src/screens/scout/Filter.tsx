import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { Box } from "../../components/Icons";
import { fmt } from "../../lib/format";
import { FilterResult, Filters } from "./types";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const FROM = ["any", "10:00", "11:00", "14:00", "15:00", "17:00", "20:00"];
const TO = ["11:30", "14:00", "17:00", "18:00", "22:00", "24:00"];
const PAY_COLOR: Record<string, string> = { cash: "#A8371F", none: "#8A8478", card: "#1E1E1C", nfc: "#5E7D4A" };

const PRESETS: { k: string; l: string; f: Partial<Filters> }[] = [
  { k: "card", l: "Card-acceptance targets", f: { status: ["OPERATIONAL"], pay: ["cash", "none"], revIdx: 3 } },
  { k: "visit", l: "Weekday afternoon visit", f: { status: ["OPERATIONAL"], days: [1, 2, 3, 4, 5], from: "14:00", to: "17:00" } },
  { k: "reach", l: "Reachable by phone", f: { status: ["OPERATIONAL"], qual: ["phone", "nochain"] } },
  { k: "estab", l: "Established (★3.5+, 50+)", f: { status: ["OPERATIONAL"], minRating: 3.5, unrated: false, revIdx: 4 } },
];

export function Filter({ runId, filters, setFilters, onBack, onNext }: {
  runId: number; filters: Partial<Filters>; setFilters: (f: Partial<Filters>) => void; onBack: () => void; onNext: () => void;
}) {
  const [res, setRes] = useState<FilterResult | null>(null);
  const [preset, setPreset] = useState("");
  const seq = useRef(0);

  useEffect(() => {
    const id = ++seq.current;
    const t = setTimeout(() => {
      api<FilterResult>(`/api/runs/${runId}/filter`, { body: filters }).then((r) => id === seq.current && setRes(r));
    }, 180);
    return () => clearTimeout(t);
  }, [runId, filters]);

  if (!res) return <div style={{ padding: 40, color: "#5E5A52" }}>Loading places…</div>;
  if (!res.total) return <div style={{ padding: 40, color: "#5E5A52" }}>This run returned no places. <button className="btn2" onClick={onBack}>← Back</button></div>;

  const f = res.filters;
  const o = res.options;
  const patch = (p: Partial<Filters>) => { setPreset(""); setFilters({ ...filters, ...p }); };
  const toggle = <T,>(key: keyof Filters, v: T) => {
    const cur = (f[key] as unknown as T[]) || [];
    patch({ [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] } as Partial<Filters>);
  };
  const maxR = Math.max(1, ...o.rating_hist);
  const maxV = Math.max(1, ...o.review_hist);
  const ratingBins = [2.0, 2.3, 2.6, 2.9, 3.2, 3.5, 3.8, 4.1, 4.4, 4.7];
  const funnelMax = res.total;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-end", gap: 16, borderBottom: "1px solid #1E1E1C", paddingBottom: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 13, color: "#5E5A52" }}>Keep the places worth a sales visit. Every filter uses fields returned by Google Maps.</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
            <span className="m" style={{ fontSize: 44, letterSpacing: "-0.02em" }}>{fmt(res.count)}</span>
            <span style={{ fontSize: 15 }}>of {fmt(res.total)} places match</span>
            <span className="m" style={{ fontSize: 12, color: "#5E5A52" }}>{((100 * res.count) / res.total).toFixed(1)}% kept</span>
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          <span style={{ fontSize: 11, color: "#5E5A52", marginRight: 4 }}>Presets</span>
          {PRESETS.map((p) => (
            <button key={p.k} className="chip" aria-pressed={preset === p.k} style={{ fontSize: 12 }}
              onClick={() => { setFilters(preset === p.k ? {} : p.f); setPreset(preset === p.k ? "" : p.k); }}>{p.l}</button>
          ))}
          <button className="btn2" onClick={() => { setFilters({}); setPreset(""); }} style={{ minHeight: 34, fontSize: 12 }}>Reset</button>
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 28, alignItems: "flex-start" }}>
        <div style={{ flex: "1 1 360px", minWidth: 0, display: "flex", flexDirection: "column" }}>
          <Group t="Business status" f="businessStatus">
            {o.status.map((s) => <Row key={s.k} on={f.status.includes(s.k)} l={s.l} n={s.n} onClick={() => toggle("status", s.k)} />)}
          </Group>

          <Group t="Rating" f="rating">
            <Bars values={o.rating_hist} max={maxR} on={(i) => ratingBins[i] + 0.3 > f.minRating} />
            <div className="slider-row"><label htmlFor="hx-fr">Minimum</label>
              <input id="hx-fr" type="range" min={0} max={4.5} step={0.1} value={f.minRating} onChange={(e) => patch({ minRating: +e.target.value })} style={{ flex: 1 }} />
              <span className="m">{f.minRating ? `★ ${f.minRating.toFixed(1)}` : "any"}</span></div>
            <button className="tog" aria-pressed={f.unrated} onClick={() => patch({ unrated: !f.unrated })}><span className="trk"><span className="knob" /></span>Keep places with no rating yet <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{fmt(o.unrated)}</span></button>
          </Group>

          <Group t="Reviews" f="userRatingCount">
            <Bars values={o.review_hist} max={maxV} on={(i) => i >= f.revIdx} />
            <div className="slider-row"><label htmlFor="hx-fv">At least</label>
              <input id="hx-fv" type="range" min={0} max={o.review_steps.length - 1} step={1} value={f.revIdx} onChange={(e) => patch({ revIdx: +e.target.value })} style={{ flex: 1 }} />
              <span className="m">{o.review_steps[f.revIdx] ? fmt(o.review_steps[f.revIdx]) : "any"}</span></div>
          </Group>

          <Group t="Opening hours" f="regularOpeningHours">
            <span style={{ fontSize: 12, color: "#5E5A52" }}>Open during your visit window</span>
            <div style={{ display: "flex", gap: 4 }}>
              {DAYS.map((d, i) => <button key={d} className="chip m" aria-pressed={f.days.includes(i)} onClick={() => toggle("days", i)} style={{ flex: 1, padding: 0, fontSize: 11, minHeight: 32 }}>{d}</button>)}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <select className="in m" aria-label="Window from" value={f.from} onChange={(e) => patch({ from: e.target.value })} style={{ flex: 1 }}>
                {FROM.map((x) => <option key={x} value={x}>{x === "any" ? "Any time" : x}</option>)}
              </select>
              <span style={{ color: "#5E5A52" }}>→</span>
              <select className="in m" aria-label="Window to" value={f.to} onChange={(e) => patch({ to: e.target.value })} style={{ flex: 1 }} disabled={f.from === "any"}>
                {TO.map((x) => <option key={x}>{x}</option>)}
              </select>
            </div>
            <button className="tog" aria-pressed={f.hasHours} onClick={() => patch({ hasHours: !f.hasHours })}><span className="trk"><span className="knob" /></span>Hours must be listed <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{fmt(o.no_hours)} missing</span></button>
          </Group>

          <Group t="Price range" f="priceRange · priceLevel">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {o.price.map((p) => <button key={p.k} className="chip" aria-pressed={f.price.includes(p.k)} onClick={() => toggle("price", p.k)} style={{ fontSize: 12, display: "inline-flex", gap: 6 }}><span className="m">{p.l}</span><span className="m" style={{ opacity: 0.6 }}>{fmt(p.n)}</span></button>)}
            </div>
          </Group>

          <Group t="Payment" f="paymentOptions">
            {o.pay.map((p) => <Row key={p.k} on={f.pay.includes(p.k)} l={p.l} n={p.n} onClick={() => toggle("pay", p.k)} />)}
          </Group>

          <Group t="Category" f="primaryType">
            <span style={{ fontSize: 12, color: "#5E5A52" }}>{f.types.length ? `${f.types.length} selected` : "All types kept · pick to narrow"}</span>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 4 }}>
              {o.types.map((t) => <Row key={t.k} on={f.types.includes(t.k)} l={t.l} n={t.n} onClick={() => toggle("types", t.k)} jp />)}
            </div>
          </Group>

          <Group t="Services" f="dineIn · takeout · reservable …">
            <span style={{ fontSize: 12, color: "#5E5A52" }}>Must offer</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {o.svc.map((s) => <button key={s.k} className="chip" aria-pressed={f.svc.includes(s.k)} onClick={() => toggle("svc", s.k)} style={{ fontSize: 12, display: "inline-flex", gap: 6 }}>{s.l}<span className="m" style={{ opacity: 0.6 }}>{fmt(s.n)}</span></button>)}
            </div>
          </Group>

          <Group t="Contact & listing quality" f="phone · website · photos">
            {o.qual.map((q) => <button key={q.k} className="tog" aria-pressed={f.qual.includes(q.k)} onClick={() => toggle("qual", q.k)}><span className="trk"><span className="knob" /></span>{q.l} <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{fmt(q.n)}</span></button>)}
          </Group>

          <Group t="Area" f="from retrieval">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 4 }}>
              {o.areas.map((a) => <Row key={a.k} on={f.areas.includes(a.k)} l={a.k === "outside" ? "Outside selected areas" : a.l} n={a.n} onClick={() => toggle("areas", a.k)} jp />)}
            </div>
          </Group>
        </div>

        <div style={{ flex: "999 1 560px", minWidth: 0, display: "flex", flexDirection: "column", gap: 22 }}>
          <div className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", paddingBottom: 8 }}><span className="lbl">What each filter removes</span><span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>in order applied</span></div>
            {res.funnel.map((r) => (
              <div key={r.l} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 2fr) 70px 64px", gap: 12, alignItems: "center", padding: "6px 0", borderTop: "1px solid #E2DDD1" }}>
                <span style={{ fontSize: 12 }}>{r.l}</span>
                <div style={{ height: 8, background: "#E2DDD1" }}><div style={{ height: 8, width: `${(100 * r.n) / funnelMax}%`, background: "#1E1E1C", transition: "width .3s ease-out" }} /></div>
                <span className="m" style={{ fontSize: 12, textAlign: "right" }}>{fmt(r.n)}</span>
                <span className="m" style={{ fontSize: 11, textAlign: "right", color: "#B33A3A" }}>{r.d ? `−${fmt(r.d)}` : ""}</span>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", paddingBottom: 8 }}>
              <span className="lbl">Preview · most reviewed first</span>
              <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{res.preview.length} of {fmt(res.count)} · hours for today (JST)</span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <div style={{ minWidth: 760 }}>
                <div className="m prev-grid prev-head"><span>PLACE</span><span>AREA</span><span>TYPE</span><span style={{ textAlign: "right" }}>★</span><span style={{ textAlign: "right" }}>REVIEWS</span><span>PRICE</span><span>PAYMENT</span><span>TODAY</span></div>
                {res.preview.map((r) => (
                  <div key={r.pk} className="prev-grid prev-row">
                    <a href={r.maps_uri} target="_blank" rel="noreferrer" className="jp" style={{ fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: "none" }}>{r.name}</a>
                    <span className="jp">{r.area}</span><span className="jp" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.type}</span>
                    <span className="m" style={{ textAlign: "right" }}>{r.rating ?? "—"}</span><span className="m" style={{ textAlign: "right" }}>{fmt(r.reviews)}</span>
                    <span className="m" style={{ fontSize: 11 }}>{r.price}</span><span style={{ fontSize: 11, color: PAY_COLOR[r.pay] }}>{r.pay_label}</span><span className="m" style={{ fontSize: 11 }}>{r.today}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", borderTop: "1px solid #D8D3C7", paddingTop: 18 }}>
            <button className="btn2" onClick={onBack}>← Back to Retrieve</button>
            <button className="btn" onClick={onNext} disabled={!res.count} style={{ minWidth: 260, justifyContent: "space-between" }}>
              <span>Continue to Summary</span><span className="m" style={{ fontSize: 12, opacity: 0.75 }}>{fmt(res.count)} places</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Group({ t, f, children }: { t: string; f: string; children: React.ReactNode }) {
  return (
    <div className="fg"><div className="fg-h"><span>{t}</span><span className="m">{f}</span></div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>{children}</div>
    </div>
  );
}

function Row({ on, l, n, onClick, jp }: { on: boolean; l: string; n: number; onClick: () => void; jp?: boolean }) {
  return (
    <button className="frow" aria-pressed={on} onClick={onClick}>
      <Box on={on} /><span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} className={jp ? "jp" : undefined}>{l}</span>
      <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{fmt(n)}</span>
    </button>
  );
}

function Bars({ values, max, on }: { values: number[]; max: number; on: (i: number) => boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 40 }}>
      {values.map((v, i) => <span key={i} title={fmt(v)} style={{ flex: 1, height: `${Math.max(2, (100 * v) / max)}%`, background: on(i) ? "#1E1E1C" : "#D8D3C7" }} />)}
    </div>
  );
}
