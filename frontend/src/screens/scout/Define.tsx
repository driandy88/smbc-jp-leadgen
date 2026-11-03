import { polygonToCells } from "h3-js";
import { KeyboardEvent, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../../api";
import { HexMap, Outline } from "../../components/HexMap";
import { Arrow, Box, Chevron, Close, HEX_TILE } from "../../components/Icons";
import { fmt, shortDate, money } from "../../lib/format";
import { Area, AreaRef, City, Estimate, Run, ScoutConfig } from "./types";

const DRAFT_KEY = "hexline.scout.draft";

type Draft = { kw: string[]; cities: string[]; areas: Record<string, string[]>; baseRes: number; maxRes: number; split: boolean; mock: boolean };

function loadDraft(cfg: ScoutConfig): Draft {
  const fallback: Draft = { kw: [], cities: ["osaka-shi"], areas: { "osaka-shi": ["27127", "27128"] }, baseRes: 8, maxRes: 10, split: true, mock: cfg.default_mock || !cfg.has_maps_key };
  try {
    return { ...fallback, ...JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}") };
  } catch {
    return fallback;
  }
}

export function Define({ cfg, lastRun, onStarted, onOpenRun }: { cfg: ScoutConfig; lastRun: Run | null; onStarted: (id: number) => void; onOpenRun: (id: number) => void }) {
  const [d, setD] = useState<Draft>(() => loadDraft(cfg));
  const [tab, setTab] = useState(cfg.keywords.groups[0].key);
  const [kwInput, setKwInput] = useState("");
  const [allCities, setAllCities] = useState<City[]>([]);
  const [cityInput, setCityInput] = useState("");
  const [areasByCity, setAreasByCity] = useState<Record<string, Area[]>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [outline, setOutline] = useState<Outline | null>(null);
  const [est, setEst] = useState<Estimate | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [runs, setRuns] = useState<Run[]>([]);

  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }));
  const maxRes = d.split ? d.maxRes : d.baseRes;
  const selected: AreaRef[] = useMemo(() => d.cities.flatMap((c) => (d.areas[c] || []).map((a) => ({ city: c, area: a }))), [d.cities, d.areas]);
  const codes = useMemo(() => selected.map((s) => s.area), [selected]);

  useEffect(() => {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(d)); } catch { /* per-viewer convenience only */ }
  }, [d]);
  useEffect(() => { api<City[]>("/api/scout/cities").then(setAllCities); api<Run[]>("/api/runs").then(setRuns); }, []);
  useEffect(() => {
    d.cities.forEach((c) => api<Area[]>(`/api/scout/cities/${c}/areas?res=${d.baseRes}`).then((a) => setAreasByCity((m) => ({ ...m, [c]: a }))));
  }, [d.cities, d.baseRes]);
  useEffect(() => {
    if (!codes.length) { setOutline(null); return; }
    api<Outline>("/api/scout/geometry", { body: codes }).then(setOutline);
  }, [codes]);
  useEffect(() => {
    const t = setTimeout(() => {
      api<Estimate>("/api/scout/estimate", { body: { keywords: d.kw, areas: selected, base_res: d.baseRes, max_res: maxRes } }).then(setEst).catch(() => setEst(null));
    }, 250);
    return () => clearTimeout(t);
  }, [d.kw, selected, d.baseRes, maxRes]);

  const previewCells = useMemo(() => {
    const out = new Set<string>();
    for (const f of outline?.features || []) {
      const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
      for (const p of polys) polygonToCells(p, d.baseRes, true).forEach((c) => out.add(c));
    }
    return [...out];
  }, [outline, d.baseRes]);

  const termInfo = useMemo(() => {
    const m = new Map<string, { en: string; hint: string }>();
    cfg.keywords.groups.forEach((g) => g.terms.forEach((t) => m.set(t.jp, t)));
    return m;
  }, [cfg]);

  const toggleKw = (t: string) => set({ kw: d.kw.includes(t) ? d.kw.filter((k) => k !== t) : [...d.kw, t] });
  const addCustom = () => {
    const t = kwInput.trim();
    if (t && !d.kw.includes(t)) set({ kw: [...d.kw, t] });
    setKwInput("");
  };
  const toggleCity = (key: string) => {
    if (d.cities.includes(key)) {
      const { [key]: _, ...rest } = d.areas;
      set({ cities: d.cities.filter((c) => c !== key), areas: rest });
    } else {
      set({ cities: [...d.cities, key] });
      setOpen((o) => ({ ...o, [key]: true }));
    }
    setCityInput("");
  };
  const toggleArea = (city: string, code: string) => {
    const cur = d.areas[city] || [];
    set({ areas: { ...d.areas, [city]: cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code] } });
  };
  const toggleWhole = (city: string) => {
    const all = (areasByCity[city] || []).map((a) => a.code);
    const whole = all.length > 0 && all.every((c) => (d.areas[city] || []).includes(c));
    set({ areas: { ...d.areas, [city]: whole ? [] : all } });
  };

  const start = async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api<{ id: number }>("/api/runs", { body: { keywords: d.kw, areas: selected, base_res: d.baseRes, max_res: maxRes, mock: d.mock } });
      onStarted(r.id);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not start the run");
      setConfirm(false);
    } finally {
      setBusy(false);
    }
  };

  const featured = allCities.slice(0, 3);
  const citySug = cityInput.trim()
    ? allCities.filter((c) => !d.cities.includes(c.key) && (c.jp.includes(cityInput.trim()) || c.en.toLowerCase().includes(cityInput.trim().toLowerCase()))).slice(0, 6)
    : [];
  const ready = d.kw.length > 0 && selected.length > 0;
  const runHint = !d.kw.length ? "Pick at least one search term." : !selected.length ? "Pick at least one area."
    : d.mock ? "Mock mode: nothing is sent to Google and nothing is billed. Results are simulated."
    : `Real API: about ${fmt(est?.expected_calls)} billable calls. You'll confirm the cost before it starts.`;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 32, alignItems: "flex-start" }}>
      <div style={{ flex: "999 1 620px", minWidth: 0, display: "flex", flexDirection: "column" }}>
        <section className="sec">
          <div className="sec-h"><span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>1.1</span><h2 className="serif h2">What to look for</h2><span className="sec-note">Pick the Google Maps terms to search. Each term is searched in every cell.</span></div>
          <div className="sec-b">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <span className="lbl">Quick packs</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {cfg.keywords.packs.map((p) => {
                  const on = p.terms.every((t) => d.kw.includes(t));
                  return (
                    <button key={p.key} className="chip" aria-pressed={on} title={p.brief} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}
                      onClick={() => set({ kw: on ? d.kw.filter((k) => !p.terms.includes(k)) : [...new Set([...d.kw, ...p.terms])] })}>
                      {p.label}<span className="m" style={{ fontSize: 10, opacity: 0.6 }}>{p.terms.length}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                <span className="lbl">Selected · {d.kw.length}</span>
                <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{d.kw.length ? `${d.kw.length} searches per cell` : ""}</span>
              </div>
              {d.kw.length === 0 ? (
                <div style={{ border: "1px dashed #CFC9BB", borderRadius: 2, padding: 16, display: "flex", alignItems: "center", gap: 14, color: "#5E5A52", fontSize: 13 }}>
                  <svg width="40" height="22" viewBox="0 0 40 22" aria-hidden="true"><path d="M2 15 Q9 4 16 12 T30 9 Q34 8 38 10" fill="none" stroke="#BDB6A7" strokeWidth="1.3" strokeLinecap="round" /></svg>
                  Nothing selected yet. Pick a quick pack, choose terms below, or type your own.
                </div>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {d.kw.map((k, i) => (
                    <span key={k} className="hx-in tag" style={{ animationDelay: `${Math.min(i, 10) * 30}ms` }}>
                      <span className="jp" style={{ fontSize: 13 }}>{k}</span>
                      <span className="m" style={{ fontSize: 11, opacity: 0.7 }}>{termInfo.get(k)?.en || "custom"}</span>
                      <button onClick={() => toggleKw(k)} aria-label={`Remove ${k}`} className="tag-x"><Close /></button>
                    </span>
                  ))}
                  <button className="btn2" onClick={() => set({ kw: [] })} style={{ minHeight: 34, fontSize: 12 }}>Clear all</button>
                </div>
              )}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                <span className="lbl">Browse terms</span><span style={{ fontSize: 11, color: "#5E5A52" }}>Japanese terms match how owners label their listings</span>
              </div>
              <div role="tablist" aria-label="Keyword categories" style={{ display: "flex", flexWrap: "wrap", borderBottom: "1px solid #D8D3C7" }}>
                {cfg.keywords.groups.map((g) => {
                  const n = g.terms.filter((t) => d.kw.includes(t.jp)).length;
                  return (
                    <button key={g.key} role="tab" aria-selected={tab === g.key} className="ktab" onClick={() => setTab(g.key)}>
                      {g.label}{n > 0 && <span className="m" style={{ fontSize: 10, marginLeft: 6, color: "#C8442B" }}>{n}</span>}
                    </button>
                  );
                })}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(190px, 100%), 1fr))", gap: 6 }}>
                {cfg.keywords.groups.find((g) => g.key === tab)!.terms.map((t) => (
                  <button key={t.jp} className="kopt" aria-pressed={d.kw.includes(t.jp)} onClick={() => toggleKw(t.jp)}>
                    <Box on={d.kw.includes(t.jp)} />
                    <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0, flex: 1 }}>
                      <span className="jp" style={{ fontSize: 14 }}>{t.jp}</span>
                      <span style={{ fontSize: 11, color: "#5E5A52" }}>{t.en}{t.hint ? ` · ${t.hint}` : ""}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div style={{ maxWidth: 420 }}>
              <label htmlFor="hx-kw" className="lbl" style={{ display: "block", paddingBottom: 6 }}>Custom term</label>
              <div style={{ display: "flex", gap: 6 }}>
                <input id="hx-kw" className="in" placeholder="Type in Japanese or English, e.g. おでん, yakitori" value={kwInput}
                  onChange={(e) => setKwInput(e.target.value)} onKeyDown={(e: KeyboardEvent) => e.key === "Enter" && addCustom()} style={{ flex: 1 }} />
                <button className="btn2" onClick={addCustom} disabled={!kwInput.trim()}>Add</button>
              </div>
              <span style={{ display: "block", fontSize: 11, color: "#5E5A52", paddingTop: 6 }}>Sent to Google exactly as typed.</span>
            </div>
          </div>
        </section>

        <section className="sec">
          <div className="sec-h"><span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>1.2</span><h2 className="serif h2">Region</h2><span className="sec-note">Choose the city first, then its areas. Boundaries: MLIT N03 (2024).</span></div>
          <div className="sec-b">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(176px, 100%), 1fr))", gap: 8 }}>
              {featured.map((c) => (
                <button key={c.key} className="cbx" aria-pressed={d.cities.includes(c.key)} onClick={() => toggleCity(c.key)}>
                  <Box on={d.cities.includes(c.key)} />
                  <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: 14 }}>{c.en || c.jp}</span>
                    <span style={{ fontSize: 11, color: "#5E5A52" }}><span className="jp">{c.jp}</span> · <span className="m">{c.areas} wards · {c.km2} km²</span></span>
                  </span>
                </button>
              ))}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
              <div style={{ position: "relative", flex: "0 1 280px" }}>
                <input className="in" placeholder="+ Add city (Osaka & Kyoto prefectures)" aria-label="Add city" value={cityInput} onChange={(e) => setCityInput(e.target.value)} style={{ width: "100%" }} />
                {citySug.length > 0 && (
                  <div className="card dropdown">
                    {citySug.map((c) => (
                      <button key={c.key} onClick={() => toggleCity(c.key)} className="dd-row">
                        <span style={{ fontSize: 13 }}>{c.en} <span className="jp" style={{ color: "#5E5A52" }}>{c.jp}</span></span>
                        <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{c.pref} · {c.km2} km²</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, flex: "1 1 300px" }}>
                {d.cities.map((key) => {
                  const c = allCities.find((x) => x.key === key);
                  return (
                    <span key={key} className="tag" style={{ fontSize: 13 }}>{c?.en || c?.jp || key} <span className="m" style={{ fontSize: 11, opacity: 0.75 }}>{(d.areas[key] || []).length} areas</span>
                      <button onClick={() => toggleCity(key)} aria-label={`Remove ${key}`} className="tag-x"><Close /></button>
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
        </section>

        <section className="sec">
          <div className="sec-h"><span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>1.3</span><h2 className="serif h2">Areas</h2><span className="sec-note">Cells shown at res {d.baseRes}. A cell belongs to the ward its centre falls in.</span></div>
          <div className="sec-b" style={{ gap: 10 }}>
            {d.cities.length === 0 && <span style={{ fontSize: 13, color: "#5E5A52" }}>Add a city above.</span>}
            {d.cities.map((key) => {
              const c = allCities.find((x) => x.key === key);
              const list = areasByCity[key] || [];
              const sel = d.areas[key] || [];
              const isOpen = open[key] ?? true;
              const whole = list.length > 0 && list.every((a) => sel.includes(a.code));
              const cellsSel = list.filter((a) => sel.includes(a.code)).reduce((s, a) => s + a.cells, 0);
              const wholeCells = list.reduce((s, a) => s + a.cells, 0);
              return (
                <div key={key} style={{ borderBottom: "1px solid #E2DDD1", paddingBottom: 10 }}>
                  <button onClick={() => setOpen({ ...open, [key]: !isOpen })} aria-expanded={isOpen} className="row-toggle">
                    <Chevron open={isOpen} />
                    <span style={{ fontSize: 15, fontWeight: 500 }}>{c?.en || c?.jp}</span><span className="jp" style={{ fontSize: 12, color: "#5E5A52" }}>{c?.jp}</span>
                    <span className="m" style={{ marginLeft: "auto", fontSize: 11, color: "#5E5A52" }}>{sel.length} of {list.length} areas · {fmt(cellsSel)} cells</span>
                  </button>
                  {isOpen && (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(190px, 100%), 1fr))", gap: 8, paddingTop: 4 }}>
                      {list.map((a) => {
                        const on = sel.includes(a.code);
                        return (
                          <button key={a.code} className="area" aria-pressed={on} onClick={() => toggleArea(key, a.code)}>
                            <svg width="58" height="44" viewBox="-34 -26 68 52" aria-hidden="true"><path d={HEX_TILE} fill={on ? "#1E1E1C" : "none"} stroke={on ? "#1E1E1C" : "#9C9586"} strokeWidth="0.9" /></svg>
                            <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                              <span style={{ fontSize: 13 }}>{a.en || a.jp}</span><span className="jp" style={{ fontSize: 11, color: "#5E5A52" }}>{a.jp}</span>
                              <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{fmt(a.cells)} cells · {a.km2} km²</span>
                            </span>
                          </button>
                        );
                      })}
                      {list.length > 1 && (
                        <button className="area" aria-pressed={whole} onClick={() => toggleWhole(key)} style={{ borderStyle: "dashed" }}>
                          <svg width="58" height="44" viewBox="-34 -26 68 52" aria-hidden="true"><path d={HEX_TILE} fill="none" stroke="#1E1E1C" strokeWidth="0.9" strokeDasharray="2 2" /><path d="M0 -8 Q4 0 8 7 Q0 7.4 -8 7 Q-4 0 0 -8 Z M0 -3 L0 2" fill="none" stroke="#C8442B" strokeWidth="1.1" strokeLinecap="round" /></svg>
                          <span style={{ display: "flex", flexDirection: "column", gap: 2 }}><span style={{ fontSize: 13 }}>Whole city</span><span className="m" style={{ fontSize: 11, color: "#A8371F" }}>{fmt(wholeCells)} cells</span></span>
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {outline && (
              <div className="card" style={{ padding: 12 }}>
                <HexMap outline={outline} layers={[{ cells: previewCells, fill: "#1E1E1C", opacity: 0.12, stroke: "#9C9586", strokeWidth: 0.5 }]} height={280} ariaLabel="Selected areas and their cells" />
              </div>
            )}
          </div>
        </section>

        <section className="sec">
          <div className="sec-h"><span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>1.4</span><h2 className="serif h2">H3 grid</h2><span className="sec-note">Google returns at most 60 places per search, so busy cells are split into 7 smaller ones and searched again.</span></div>
          <div className="sec-b">
            <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
              <label htmlFor="hx-res" className="lbl" style={{ width: 150 }}>Base resolution</label>
              <input id="hx-res" type="range" min={7} max={10} step={1} value={d.baseRes} onChange={(e) => { const r = +e.target.value; set({ baseRes: r, maxRes: Math.max(d.maxRes, r) }); }} style={{ flex: "1 1 260px" }} />
              <span className="m" style={{ fontSize: 13, width: 50 }}>res {d.baseRes}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", border: "1px solid #D8D3C7" }}>
              {(est?.by_res || [7, 8, 9, 10].map((r) => ({ res: r, km2: 0, cells: null }))).map((r) => (
                <button key={r.res} onClick={() => set({ baseRes: r.res, maxRes: Math.max(d.maxRes, r.res) })} style={{ font: "inherit", textAlign: "left", cursor: "pointer", border: "none", padding: 12, display: "flex", flexDirection: "column", gap: 4, borderLeft: "1px solid #D8D3C7", ...(r.res === d.baseRes ? { background: "#1E1E1C", color: "#F3F0E8" } : { background: "transparent", color: "#1E1E1C" }) }}>
                  <span className="m" style={{ fontSize: 12 }}>res {r.res}</span>
                  <span className="m" style={{ fontSize: 11, opacity: 0.75 }}>≈ {r.km2} km² / cell</span>
                  <span className="m" style={{ fontSize: 18, marginTop: 6 }}>{fmt(r.cells)}</span>
                  <span style={{ fontSize: 11, opacity: 0.75 }}>cells in selection</span>
                </button>
              ))}
            </div>
            <button className="tog" aria-pressed={d.split} onClick={() => set({ split: !d.split })}><span className="trk"><span className="knob" /></span>Auto-split saturated hexes</button>
            {d.split && (
              <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                <label htmlFor="hx-max" className="lbl" style={{ width: 150 }}>Max split resolution</label>
                <input id="hx-max" type="range" min={d.baseRes + 1} max={11} step={1} value={Math.max(d.maxRes, d.baseRes + 1)} onChange={(e) => set({ maxRes: +e.target.value })} style={{ flex: "1 1 260px" }} disabled={d.baseRes >= 11} />
                <span className="m" style={{ fontSize: 13, width: 50 }}>res {Math.max(d.maxRes, d.baseRes + 1)}</span>
              </div>
            )}
            <span style={{ fontSize: 12, color: "#5E5A52", lineHeight: 1.5 }}>
              Recommended: res 8 → split to 10. A cell that still returns 60 at the max resolution is marked saturated (some places missed).
            </span>
          </div>
        </section>
      </div>

      <aside style={{ flex: "0 1 300px", minWidth: 0, position: "sticky", top: 24, alignSelf: "flex-start", display: "flex", flexDirection: "column", gap: 12 }}>
        <div role="radiogroup" aria-label="Data source" className="seg">
          <button role="radio" aria-checked={!d.mock} onClick={() => set({ mock: false })} disabled={!cfg.has_maps_key} title={cfg.has_maps_key ? "" : "No Maps API key configured"}>Real API</button>
          <button role="radio" aria-checked={d.mock} onClick={() => set({ mock: true })}>Mock</button>
        </div>
        <div className="card" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="lbl">Estimate</span>
          {[
            ["Cells", fmt(est?.cells)], ["Searches (cell × term)", fmt(est?.tasks)],
            ["API calls, expected", fmt(est?.expected_calls)], ["API calls, minimum", fmt(est?.min_calls)],
            ...(est?.duration ? [["Time, real API", `≈ ${mins(est.duration.minutes)} · ${est.duration.workers} in parallel`]] : []),
          ].map(([l, v]) => (
            <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}><span style={{ color: "#5E5A52" }}>{l}</span><span className="m">{v}</span></div>
          ))}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", borderTop: "1px solid #E2DDD1", paddingTop: 8 }}>
            <span style={{ fontSize: 13 }}>{d.mock ? "Would cost" : "Cost"}</span>
            <span className="m" style={{ fontSize: 20, textDecoration: d.mock ? "line-through" : undefined, color: d.mock ? "#8A8478" : undefined }}>{money(est?.expected_local)}</span>
          </div>
          <span className="m" style={{ fontSize: 10, color: "#8A8478", lineHeight: 1.5 }}>
            {cfg.sku} · ${(cfg.usd_per_call * 1000).toFixed(0)}/1k calls · {cfg.currency} {cfg.usd_rate}/USD · {est?.calls_per_task ?? "—"} calls per search ({est?.basis === "history" ? "from past runs" : "default guess"})
          </span>
        </div>
        <button className="btn" onClick={() => (d.mock ? start() : setConfirm(true))} disabled={!ready || busy} style={{ minHeight: 56, justifyContent: "space-between", width: "100%" }}>
          <span>{busy ? "Starting…" : "Retrieve places"}</span><Arrow />
        </button>
        <span style={{ fontSize: 12, color: d.mock ? "#5E5A52" : "#A8371F", lineHeight: 1.5 }}>{runHint}</span>
        {err && <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>}

        {runs.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", borderTop: "1px solid #D8D3C7", paddingTop: 12, gap: 2 }}>
            <span className="lbl" style={{ paddingBottom: 6 }}>Recent runs</span>
            {runs.slice(0, 6).map((r) => (
              <button key={r.id} className="frow" disabled={r.status !== "done"} onClick={() => onOpenRun(r.id)} style={{ justifyContent: "space-between", opacity: r.status === "done" ? 1 : 0.6 }}
                title={r.status === "done" ? "Open in Filter" : r.error || r.status}>
                <span className="m" style={{ fontSize: 11 }}>#{r.id} · {shortDate(r.created_at)}{r.mock ? " · mock" : ""}{r.id === lastRun?.id ? " · latest" : ""}</span>
                <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>{r.status === "done" ? `${fmt(r.unique_places)} places` : r.status}</span>
              </button>
            ))}
          </div>
        )}
      </aside>

      {confirm && est && (
        <div role="dialog" aria-modal="true" aria-label="Confirm cost" className="overlay" onClick={() => setConfirm(false)}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ padding: 24, width: "min(440px, 100%)", display: "flex", flexDirection: "column", gap: 14, background: "#F3F0E8" }}>
            <span className="m" style={{ fontSize: 11, color: "#C8442B" }}>REAL API · BILLED</span>
            <h3 className="serif" style={{ margin: 0, fontWeight: 400, fontSize: 24 }}>Start a billed run?</h3>
            <div style={{ fontSize: 14, lineHeight: 1.6 }}>
              {fmt(est.cells)} cells × {est.keywords} terms = {fmt(est.tasks)} searches. Expect about <b className="m">{fmt(est.expected_calls)}</b> calls,
              roughly <b className="m">{money(est.expected_local)}</b> (at least {money(est.min_local)}). Splits in busy areas can push it higher.
              {est.duration && <> Takes about <b className="m">{mins(est.duration.minutes)}</b> with {est.duration.workers} searches in parallel (one at a time: {mins(est.duration.minutes_sequential)}).</>}
            </div>
            <span style={{ fontSize: 12, color: "#5E5A52" }}>Every call is logged in the billing ledger. You can cancel at any time; calls already made are billed.</span>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn2" onClick={() => setConfirm(false)}>Back</button>
              <button className="btn" onClick={start} disabled={busy}>Run for ≈ {money(est.expected_local)}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const mins = (m: number) => (m < 1 ? "<1 min" : m < 90 ? `${Math.round(m)} min` : `${(m / 60).toFixed(1)} h`);
