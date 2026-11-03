import { useEffect, useState } from "react";
import { api, ApiError, download } from "../../api";
import type { Outline } from "../../components/HexMap";
import { PlaceMap, Points } from "../../components/PlaceMap";
import { Squiggle } from "../../components/Icons";
import { cityName, fmt, shortDate, money } from "../../lib/format";
import { AiBrief, Brief } from "./AiBrief";
import { Hotspots, MainOverview, TopMerchants } from "./Business";
import { Profile, Version } from "./types";

type Analysis = { profile: Profile; summary: Brief };

export function Analysis({ onDataChip }: { onDataChip: (s: string) => void }) {
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [result, setResult] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [outline, setOutline] = useState<Outline | null>(null);

  useEffect(() => {
    api<Version[]>("/api/versions").then((v) => {
      setVersions(v);
      if (v[0]) setSel(v[0].id);
    });
  }, []);

  const v = versions?.find((x) => x.id === sel) || null;
  useEffect(() => {
    setResult(null);
    setErr("");
    if (!v) return;
    onDataChip(v.name);
    if (v.analyzed) api<Analysis>(`/api/versions/${v.id}/analysis`).then((a) => a.profile && setResult(a));
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const areas = result?.profile?.run?.areas;
    if (areas) api<Outline>("/api/scout/geometry", { body: areas.map((a: { area: string }) => a.area) }).then(setOutline);
  }, [result]);

  const analyze = async () => {
    if (!v) return;
    setBusy(true);
    setErr("");
    try {
      setResult(await api<Analysis>(`/api/versions/${v.id}/analyze`, { method: "POST" }));
      setVersions((vs) => vs && vs.map((x) => (x.id === v.id ? { ...x, analyzed: true } : x)));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  };

  if (!versions) return null;
  if (!versions.length) return <div style={{ padding: "40px 0", color: "#5E5A52", fontSize: 14 }}>No saved versions yet. Run a retrieval, filter it and save it from the Summary step.</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 1000 }}>
          <div className="m vrow" style={{ cursor: "default", fontSize: 10, color: "#5E5A52", letterSpacing: "0.05em", borderTop: "1px solid #1E1E1C", minHeight: 36, padding: 8 }}>
            <span /><span>VERSION</span><span>DATE</span><span>CITIES</span><span style={{ textAlign: "right" }}>AREAS</span><span style={{ textAlign: "right" }}>KW</span><span style={{ textAlign: "right" }}>ROWS</span><span style={{ textAlign: "right" }}>DIFF</span><span style={{ textAlign: "right" }}>API COST</span><span>AUTHOR</span>
          </div>
          {versions.map((x, i) => (
            <button key={x.id} className="vrow" aria-pressed={x.id === sel} onClick={() => setSel(x.id)} title={x.notes}>
              <span className="rad">{x.id === sel && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#C8442B" }} />}</span>
              <span className="m" style={{ display: "flex", gap: 8, alignItems: "center", overflow: "hidden" }}>{x.name}{i === 0 && <span className="latest">latest</span>}{x.mock && <span className="mock-tag">mock</span>}</span>
              <span className="m">{shortDate(x.created_at)}</span><span>{x.cities.map(cityName).join(", ")}</span>
              <span className="m" style={{ textAlign: "right" }}>{x.areas}</span><span className="m" style={{ textAlign: "right" }}>{x.keywords}</span>
              <span className="m" style={{ textAlign: "right" }}>{fmt(x.rows)}</span>
              <span className="m" style={{ textAlign: "right", color: (x.diff ?? 0) >= 0 ? "#5E7D4A" : "#B33A3A" }}>{x.diff == null ? "—" : `${x.diff >= 0 ? "+" : ""}${fmt(x.diff)}`}</span>
              <span className="m" style={{ textAlign: "right" }}>{x.mock ? `(${money(x.cost_local)})` : money(x.cost_local)}</span>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{x.author.split("@")[0]}</span>
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: "#5E5A52" }}>Selected <span className="m" style={{ color: "#1E1E1C" }}>{v?.name}</span> · {fmt(v?.rows)} rows{v?.notes ? ` · ${v.notes}` : ""}</span>
        <div style={{ display: "flex", gap: 8 }}>
          {v && <button className="btn2" onClick={() => download(`/api/versions/${v.id}/export.csv`, `${v.name}.csv`)}>Export CSV</button>}
          <button className="btn" onClick={analyze} disabled={!v || busy}>{result ? "Re-analyze" : "Analyze"}</button>
        </div>
      </div>
      {err && <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>}

      {busy && (
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "40px 0", justifyContent: "center" }}>
          <Squiggle w={160} /><span style={{ fontSize: 13, color: "#5E5A52" }}>Profiling {fmt(v?.rows)} rows{v?.mock ? "" : " and asking Claude"}…</span>
        </div>
      )}

      {result && !busy && v && <Report key={v.id} a={result} versionId={v.id} name={v.name} outline={outline} />}
    </div>
  );
}

function Report({ a, versionId, name, outline }: { a: Analysis; versionId: number; name: string; outline: Outline | null }) {
  const [points, setPoints] = useState<Points | null>(null);
  useEffect(() => { api<Points>(`/api/versions/${versionId}/points`).then(setPoints); }, [versionId]);
  const p = a.profile;

  return (
    <div className="hx-in" style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <AiBrief s={a.summary} name={name} />

      <Section n="01" t="Main" />
      <MainOverview p={p} points={points} />

      <Section n="02" t="Map & density" />
      <Card title="Merchant map · every place in this version" meta="red circles = densest F&B neighbourhoods">
        <PlaceMap points={points} outline={outline} hotspots={p.hotspots} />
      </Card>
      <Hotspots p={p} />

      <Section n="03" t="Top merchants" />
      <TopMerchants points={points} />
    </div>
  );
}

const Section = ({ n, t }: { n: string; t: string }) => (
  <div style={{ display: "flex", alignItems: "baseline", gap: 10, borderBottom: "1px solid #1E1E1C", paddingBottom: 8, marginBottom: -12 }}>
    <span className="m" style={{ fontSize: 11, color: "#C8442B" }}>{n}</span>
    <h2 className="serif" style={{ margin: 0, fontWeight: 400, fontSize: 26 }}>{t}</h2>
  </div>
);

function Card({ title, meta, children }: { title: string; meta: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><span className="lbl">{title}</span><span className="m" style={{ fontSize: 11, color: "#5E5A52", textAlign: "right" }}>{meta}</span></div>
      {children}
    </div>
  );
}
