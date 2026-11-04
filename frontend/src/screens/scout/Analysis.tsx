import { useEffect, useState } from "react";
import { api, ApiError, download } from "../../api";
import type { Outline } from "../../components/HexMap";
import { PlaceMap, Points } from "../../components/PlaceMap";
import { Squiggle } from "../../components/Icons";
import { cityName, fmt, shortDate, money } from "../../lib/format";
import { AiBrief, Brief } from "./AiBrief";
import { Hotspots, MainOverview, TopCategories } from "./Business";
import { Profile, Version } from "./types";

type Analysis = { profile: Profile; summary: Brief };
type CombineStats = { rows_in: number; rows: number; duplicates: number };

export function Analysis({ onDataChip }: { onDataChip: (s: string) => void }) {
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [result, setResult] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [outline, setOutline] = useState<Outline | null>(null);
  const [picked, setPicked] = useState<number[] | null>(null); // null = not combining

  useEffect(() => {
    api<Version[]>("/api/versions").then((v) => {
      setVersions(v);
      if (v[0]) setSel(v[0].id);
    });
  }, []);

  const combined = (c: Version) => {
    setVersions((vs) => [c, ...(vs || [])]);
    setSel(c.id);
    setPicked(null);
  };

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
            <button key={x.id} className="vrow" aria-pressed={picked ? picked.includes(x.id) : x.id === sel} title={x.sources ? `Combined from ${x.sources.map((s) => s.name).join(" + ")}${x.notes ? ` · ${x.notes}` : ""}` : x.notes}
              onClick={() => picked ? setPicked(picked.includes(x.id) ? picked.filter((id) => id !== x.id) : [...picked, x.id]) : setSel(x.id)}>
              {picked
                ? <span className="pick" aria-hidden="true">{picked.includes(x.id) && "✓"}</span>
                : <span className="rad">{x.id === sel && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#C8442B" }} />}</span>}
              <span className="m" style={{ display: "flex", gap: 8, alignItems: "center", overflow: "hidden" }}>{x.name}{i === 0 && <span className="latest">latest</span>}{x.sources && <span className="latest" style={{ borderColor: "#1E1E1C", color: "#1E1E1C" }}>combined · {x.sources.length}</span>}{x.mock && <span className="mock-tag">mock</span>}</span>
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

      {picked ? <CombinePanel versions={versions} picked={picked} onCancel={() => setPicked(null)} onDone={combined} /> : (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "#5E5A52" }}>Selected <span className="m" style={{ color: "#1E1E1C" }}>{v?.name}</span> · {fmt(v?.rows)} rows{v?.sources ? ` · combined from ${v.sources.map((s) => s.name).join(" + ")}` : ""}{v?.notes ? ` · ${v.notes}` : ""}</span>
          <div style={{ display: "flex", gap: 8 }}>
            {versions.length > 1 && <button className="btn2" onClick={() => setPicked([])} disabled={busy}>Combine versions…</button>}
            {v && <button className="btn2" onClick={() => download(`/api/versions/${v.id}/export.csv`, `${v.name}.csv`)}>Export CSV</button>}
            <button className="btn" onClick={analyze} disabled={!v || busy}>{result ? "Re-analyze" : "Analyze"}</button>
          </div>
        </div>
      )}
      {err && <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>}

      {busy && (
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "40px 0", justifyContent: "center" }}>
          <Squiggle w={160} /><span style={{ fontSize: 13, color: "#5E5A52" }}>Profiling {fmt(v?.rows)} rows{v?.mock ? "" : " and asking the AI"}…</span>
        </div>
      )}

      {result && !busy && v && !picked && <Report key={v.id} a={result} versionId={v.id} name={v.name} outline={outline} />}
    </div>
  );
}

/** Pick versions in the table above; the new version holds each place once and the sources stay as they are. */
function CombinePanel({ versions, picked, onCancel, onDone }: { versions: Version[]; picked: number[]; onCancel: () => void; onDone: (v: Version) => void }) {
  const [name, setName] = useState(() => `combined_${new Date().toISOString().slice(0, 10)}_v${versions.length + 1}`);
  const [notes, setNotes] = useState("");
  const [stats, setStats] = useState<CombineStats | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const names = picked.map((id) => versions.find((x) => x.id === id)?.name).filter(Boolean);

  useEffect(() => {
    setStats(null);
    if (picked.length < 2) return;
    let live = true;
    api<CombineStats>("/api/versions/combine", { body: { version_ids: picked, dry_run: true } }).then((s) => live && setStats(s)).catch(() => {});
    return () => { live = false; };
  }, [picked.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async () => {
    setBusy(true);
    setErr("");
    try {
      onDone(await api<Version>("/api/versions/combine", { body: { version_ids: picked, name, notes } }));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Combine failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" aria-label="Combine versions" style={{ padding: 22, display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "baseline" }}>
        <span className="lbl">Combine versions</span>
        <span style={{ fontSize: 13, color: "#5E5A52" }}>
          {picked.length < 2 ? "Tick two or more versions in the table above." : names.join(" + ")}
        </span>
      </div>
      {picked.length >= 2 && (
        <div className="m" style={{ display: "flex", gap: 28, flexWrap: "wrap", fontSize: 13 }} aria-live="polite">
          {stats ? (
            <>
              <span><span style={{ fontSize: 24 }}>{fmt(stats.rows_in)}</span> rows in</span>
              <span style={{ color: "#B33A3A" }}><span style={{ fontSize: 24 }}>−{fmt(stats.duplicates)}</span> duplicates</span>
              <span><span style={{ fontSize: 24, color: "#C8442B" }}>{fmt(stats.rows)}</span> unique merchants</span>
            </>
          ) : <span style={{ color: "#5E5A52" }}>Counting…</span>}
        </div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "16px 24px", alignItems: "flex-end" }}>
        <div style={{ flex: "1 1 280px", display: "flex", flexDirection: "column", gap: 6 }}>
          <label htmlFor="hx-cn" className="lbl">New version name</label>
          <input id="hx-cn" className="in m" value={name} onChange={(e) => setName(e.target.value)} style={{ fontSize: 14 }} />
        </div>
        <div style={{ flex: "2 1 360px", display: "flex", flexDirection: "column", gap: 6 }}>
          <label htmlFor="hx-cnote" className="lbl">Notes</label>
          <input id="hx-cnote" className="in" placeholder="e.g. Kita + Minami, all keywords" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn2" onClick={onCancel} disabled={busy}>Cancel</button>
          <button className="btn" onClick={create} disabled={busy || picked.length < 2 || !name.trim()}>{busy ? "Combining…" : "Create combined version"}</button>
        </div>
      </div>
      {err && <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>}
      <span style={{ fontSize: 11, color: "#8A8478" }}>The versions you pick are kept as they are. A merchant found in several keeps its newest data. Analyze the new version once it's created.</span>
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

      <Section n="03" t="Top categories" />
      <TopCategories points={points} />
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
