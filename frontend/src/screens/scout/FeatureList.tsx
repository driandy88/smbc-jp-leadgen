import { Fragment, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../../api";
import { fmt, pct } from "../../lib/format";
import { SheetButton } from "./Websites";

type Val = string | number | boolean;
type Row = {
  path: string; parent: string | null; key: string; depth: number; label: string; kind: string;
  places: number; pct: number; pct_parent: number; children: number; nested: number;
  distinct: number; distinct_capped: boolean; top: [Val, number][]; values: number; example: Val | null;
  num?: { min: number; median: number; max: number }; items?: { mean: number; max: number }; text?: { mean: number; max: number };
  unique: boolean; free_text: boolean;
};
type Band = { k: string; l: string; min: number };
type Summary = { merchants: number; features: number; nested: number; with_nested: number; usable: number;
  bands: Record<string, number>; bands_nested: Record<string, number>; band_names: Band[]; rows: Row[] };

const COL: Record<string, string> = { complete: "#1E1E1C", mostly: "#6B675E", partial: "#B59A5B", rare: "#C8442B" };
const KINDS = ["yes/no", "number", "text", "list", "object"];
const SHOWN = 20;
const band = (bands: Band[], p: number) => bands.find((b) => p >= b.min)!;
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
// Share of a value: of merchants for a list of plain values (a merchant lists each once), else of all values seen
const share = (r: Row, c: number) => (100 * c) / Math.max(1, r.kind === "list" ? r.places : r.values);
// Hardly any value repeats: addresses, phone numbers, IDs
const mostlyUnique = (r: Row) => r.unique || (r.distinct > 50 && r.top.length > 0 && r.top[0][1] / Math.max(1, r.values) < 0.01);
const show = (v: Val | null) => (v === true ? "Yes" : v === false ? "No" : v == null ? "—" : String(v));

/** In one line: what the field holds. */
function gist(r: Row) {
  if (r.free_text) return `Free text · ~${fmt(r.text!.mean)} characters`;
  if (mostlyUnique(r)) return `Different per merchant · e.g. ${show(r.example)}`;
  if (!r.top.length) return r.kind === "object" ? `Holds ${plural(r.children, "field")}` : r.kind === "list" ? `List of items, each with ${plural(r.children, "field")}` : "—";
  return r.top.slice(0, 3).map(([v, c]) => `${show(v)} ${pct(share(r, c), 0)}`).join(" · ");
}

/** Every field Google returns for the merchants, most complete first, with nested fields broken down. */
export function FeatureList({ versionId }: { versionId: number }) {
  const [s, setS] = useState<Summary | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("all");
  const [bnd, setBnd] = useState("all");
  const [flat, setFlat] = useState(false);
  const [others, setOthers] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    setS(null);
    api<Summary>(`/api/versions/${versionId}/features`).then(setS).catch((e) => setErr(e instanceof ApiError ? e.message : "Couldn't load the feature list"));
  }, [versionId]);

  const list = useMemo(() => {
    if (!s) return [];
    const t = q.trim().toLowerCase();
    // A search or the nested switch lists sub-fields as rows too; otherwise top-level features only
    return s.rows.filter((r) => (flat || t ? true : !r.parent)
      && (!t || r.path.toLowerCase().includes(t) || r.label.toLowerCase().includes(t))
      && (kind === "all" || r.kind === kind)
      && (bnd === "all" || band(s.band_names, r.pct).k === bnd));
  }, [s, q, kind, bnd, flat]);

  if (err) return <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>;
  if (!s) return <span style={{ fontSize: 12, color: "#5E5A52" }}>Profiling every field of every merchant… the first time takes up to a minute.</span>;
  const top = s.rows.filter((r) => !r.parent);
  const filtered = q.trim() !== "" || kind !== "all" || bnd !== "all" || flat;
  const head = list.slice(0, SHOWN);
  const rest = list.slice(SHOWN);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5, maxWidth: 980 }}>
        Google gives <b>{s.features} features</b> per merchant, and {s.with_nested} of them nest another <b>{s.nested} sub-fields</b>.
        {" "}<b>{s.usable} are usable</b>: filled for at least half of the {fmt(s.merchants)} merchants. {s.bands.complete} are near complete (90%+).
      </p>

      <div className="web-tiles">
        {s.band_names.map((b) => (
          <button key={b.k} className="web-tile" style={{ minHeight: 0, cursor: "pointer", background: bnd === b.k ? "#F1EEE6" : "transparent" }}
            aria-pressed={bnd === b.k} onClick={() => setBnd(bnd === b.k ? "all" : b.k)}>
            <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}><span style={{ width: 9, height: 9, background: COL[b.k] }} />{b.l}</span>
            <span className="m" style={{ fontSize: 24, letterSpacing: "-0.02em" }}>{s.bands[b.k]}</span>
            <span style={{ fontSize: 11, color: "#5E5A52" }}>{b.min ? `filled for ${b.min}%+` : "under 10%"} · {s.bands_nested[b.k]} sub-fields</span>
          </button>
        ))}
        <div className="web-tile" style={{ minHeight: 0 }}>
          <span style={{ fontSize: 12 }}>Full profile</span>
          <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.4 }}>Top 20 and others, every nested field broken down, top values and ranges.</span>
          <span style={{ marginTop: "auto" }}><SheetButton path={`/api/versions/${versionId}/sheets/features`} primary /></span>
        </div>
      </div>

      <div style={{ display: "flex", height: 14, gap: 1 }} aria-label="Features by completeness">
        {top.map((r) => <span key={r.path} title={`${r.label}: ${pct(r.pct)}`} style={{ flex: 1, background: COL[band(s.band_names, r.pct).k] }} />)}
      </div>

      <div className="rv-controls">
        <label className="wf-field">
          <span className="lbl">Find a feature</span>
          <input className="in" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. payment, parking, credit" style={{ width: 220 }} />
        </label>
        <label className="wf-field">
          <span className="lbl">Type</span>
          <select className="in" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="all">All types</option>
            {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </label>
        <label className="wf-field">
          <span className="lbl">Completeness</span>
          <select className="in" value={bnd} onChange={(e) => setBnd(e.target.value)}>
            <option value="all">Any</option>
            {s.band_names.map((b) => <option key={b.k} value={b.k}>{b.l} ({b.min ? `${b.min}%+` : "under 10%"})</option>)}
          </select>
        </label>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, alignSelf: "flex-end", minHeight: 34 }}>
          <input type="checkbox" checked={flat} onChange={(e) => setFlat(e.target.checked)} />List nested sub-fields as rows
        </label>
        {filtered && <button className="chip" style={{ alignSelf: "flex-end" }} onClick={() => { setQ(""); setKind("all"); setBnd("all"); setFlat(false); }}>Clear filters</button>}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <span className="lbl">{filtered ? `${list.length} match` : `Top ${SHOWN} · most complete first`}</span>
        <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>click a row to see what is inside</span>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="rv-table">
          <thead><tr><th>#</th><th>Feature</th><th>Type</th><th style={{ width: 180 }}>Completeness</th><th className="r">Merchants</th><th className="r">Sub-fields</th><th>What's in it</th></tr></thead>
          <tbody>
            {head.map((r, i) => <FeatureRow key={r.path} r={r} i={i + 1} s={s} open={open} setOpen={setOpen} />)}
            {rest.length > 0 && (
              <tr><td colSpan={7} style={{ padding: 0 }}>
                <button className="chip" style={{ margin: "8px 0", width: "100%", justifyContent: "space-between", display: "flex" }} aria-expanded={others} onClick={() => setOthers(!others)}>
                  <span>Others · {rest.length} {flat || q ? "fields" : "features"}, filled for {pct(Math.min(...rest.map((r) => r.pct)), 0)}–{pct(Math.max(...rest.map((r) => r.pct)), 0)} of merchants</span>
                  <span>{others ? "Hide ▴" : "Show ▾"}</span>
                </button>
              </td></tr>
            )}
            {others && rest.map((r, i) => <FeatureRow key={r.path} r={r} i={SHOWN + i + 1} s={s} open={open} setOpen={setOpen} />)}
            {!list.length && <tr><td colSpan={7} style={{ color: "#5E5A52", padding: "14px 0" }}>No feature matches. Try another word or clear the filters.</td></tr>}
          </tbody>
        </table>
      </div>

      <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.5, maxWidth: 980 }}>
        Completeness = merchants with a value in the field ÷ all {fmt(s.merchants)} merchants. "No" counts as a value; empty text or lists don't.
        Nested fields read as a path: <span className="m">paymentOptions.acceptsCreditCards</span> is a field inside an object,
        {" "}<span className="m">reviews[].rating</span> a field inside each item of a list.
      </span>
    </div>
  );
}

function Bar({ p, color }: { p: number; color: string }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ flex: 1, height: 8, background: "#ECE8DF" }}><span style={{ display: "block", height: 8, width: `${p}%`, background: color }} /></span>
      <span className="m" style={{ width: 44, textAlign: "right" }}>{pct(p, p >= 99.95 || p < 0.05 ? 0 : 1)}</span>
    </span>
  );
}

function FeatureRow({ r, i, s, open, setOpen }: { r: Row; i: number; s: Summary; open: string | null; setOpen: (p: string | null) => void }) {
  const isOpen = open === r.path;
  const b = band(s.band_names, r.pct);
  return (
    <Fragment>
      <tr onClick={() => setOpen(isOpen ? null : r.path)} style={{ cursor: "pointer", background: isOpen ? "#F6F4EE" : undefined }} aria-expanded={isOpen}>
        <td className="m">{i}</td>
        <td>{r.label}<span className="m" style={{ display: "block", fontSize: 10, color: "#8A8478" }}>{r.path}</span></td>
        <td className="m" style={{ fontSize: 11 }}>{r.kind}</td>
        <td title={b.l}><Bar p={r.pct} color={COL[b.k]} /></td>
        <td className="m r">{fmt(r.places)}</td>
        <td className="m r">{r.nested || "—"}</td>
        <td style={{ fontSize: 11, color: "#5E5A52", maxWidth: 360 }}>{gist(r)}</td>
      </tr>
      {isOpen && <tr><td /><td colSpan={6} style={{ padding: "4px 0 16px" }}><Detail r={r} s={s} /></td></tr>}
    </Fragment>
  );
}

/** The profile of one field: what values it holds and, for an object or list, every field nested inside. */
function Detail({ r, s }: { r: Row; s: Summary }) {
  const [pick, setPick] = useState<string | null>(null);
  const kids = s.rows.filter((k) => k.path.startsWith(r.path + ".") || k.path.startsWith(r.path + "[]."))
    .sort((a, b) => (a.path < b.path ? -1 : 1));
  const picked = kids.find((k) => k.path === pick);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Facts r={r} />
      {r.top.length > 0 && !mostlyUnique(r) && <Values r={r} />}
      {kids.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="lbl">Inside · {plural(kids.length, "sub-field")}</span>
          <table className="rv-table" style={{ minWidth: 640 }}>
            <thead><tr><th>Sub-field</th><th>Type</th><th style={{ width: 160 }}>Of all merchants</th><th className="r" title={`Of merchants that have ${r.label.toLowerCase()}`}>Of those with it</th><th>What's in it</th></tr></thead>
            <tbody>
              {kids.map((k) => (
                <Fragment key={k.path}>
                  <tr onClick={() => setPick(pick === k.path ? null : k.path)} style={{ cursor: "pointer", background: pick === k.path ? "#F1EEE6" : undefined }}>
                    <td style={{ paddingLeft: 12 * (k.depth - r.depth - 1) }}>
                      {k.label}<span className="m" style={{ display: "block", fontSize: 10, color: "#8A8478" }}>{k.path.slice(r.path.length)}</span>
                    </td>
                    <td className="m" style={{ fontSize: 11 }}>{k.kind}</td>
                    <td><Bar p={k.pct} color={COL[band(s.band_names, k.pct).k]} /></td>
                    <td className="m r">{pct(k.pct_parent, 0)}</td>
                    <td style={{ fontSize: 11, color: "#5E5A52" }}>{gist(k)}</td>
                  </tr>
                  {picked === k && <tr><td colSpan={5} style={{ padding: "4px 0 12px 12px" }}><Facts r={k} />{k.top.length > 0 && !mostlyUnique(k) && <Values r={k} />}</td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Facts({ r }: { r: Row }) {
  const f: [string, string][] = [["Filled for", `${fmt(r.places)} merchants`]];
  if (r.distinct) f.push(["Distinct values", r.distinct_capped ? `${fmt(r.distinct)}+` : fmt(r.distinct)]);
  if (r.num) f.push(["Min · median · max", `${r.num.min} · ${r.num.median} · ${r.num.max}`]);
  if (r.items) f.push(["Items per merchant", `${r.items.mean.toFixed(1)} on average, up to ${r.items.max}`]);
  if (r.text) f.push(["Text length", `${fmt(r.text.mean)} characters on average, up to ${fmt(r.text.max)}`]);
  if (r.example != null) f.push(["Example", show(r.example)]);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 22px", fontSize: 12 }}>
      {f.map(([k, v]) => <span key={k}><span className="lbl" style={{ marginRight: 6 }}>{k}</span>{v}</span>)}
    </div>
  );
}

function Values({ r }: { r: Row }) {
  const max = Math.max(...r.top.map(([, c]) => c));
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(120px, 280px) 1fr 70px", gap: "3px 10px", fontSize: 12, maxWidth: 720, marginTop: 6 }}>
      {r.top.map(([v, c]) => (
        <Fragment key={String(v)}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={show(v)}>{show(v)}</span>
          <span style={{ alignSelf: "center", height: 8, background: "#ECE8DF" }}><span style={{ display: "block", height: 8, width: `${(100 * c) / max}%`, background: "#6B675E" }} /></span>
          <span className="m r" style={{ textAlign: "right" }}>{fmt(c)} <span className="rv-of">{pct(share(r, c), 0)}</span></span>
        </Fragment>
      ))}
      {r.distinct > r.top.length && <span style={{ gridColumn: "1 / -1", fontSize: 11, color: "#8A8478" }}>+ {r.distinct_capped ? `${fmt(r.distinct)}+` : fmt(r.distinct - r.top.length)} other values</span>}
    </div>
  );
}
