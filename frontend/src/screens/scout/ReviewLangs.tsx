import { useEffect, useState } from "react";
import { api, ApiError } from "../../api";
import { fmt, pct } from "../../lib/format";
import { SheetButton } from "./Websites";

type Split = { ja: number; en: number; other: number; n: number; ja_pct: number; en_pct: number; other_pct: number };
type Top = { place_id: string; name: string; area: string; segment: string; rating: number | null; reviews: number; sample: number;
  ja: number; en: number; other: number; other_langs: string; est_ja: number; est_en: number; maps_uri: string | null; callable: boolean };
type ByRow = Split & { key: string; merchants: number; foreign_merchants: number; foreign_pct: number };
type Summary = { covered: number; merchants: number; sampled?: number; total_reviews?: number; split?: Split;
  langs?: { code: string; name: string; n: number }[]; foreign_merchants?: number; by_area?: ByRow[]; areas?: string[] };

const C = { ja: "#1E1E1C", en: "#C8442B", other: "#B59A5B" };
const GROUPS: [keyof typeof C, string][] = [["ja", "Japanese"], ["en", "English"], ["other", "Other languages"]];

/** Who reviews the merchants: Japanese locals or visitors. Measured on the up-to-5 reviews Google returns per place. */
export function ReviewLangs({ versionId }: { versionId: number }) {
  const [s, setS] = useState<Summary | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api<Summary>(`/api/versions/${versionId}/reviews`).then(setS).catch((e) => setErr(e instanceof ApiError ? e.message : "Couldn't load reviews"));
  }, [versionId]);

  if (err) return <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>;
  if (!s) return <span style={{ fontSize: 12, color: "#5E5A52" }}>Reading reviews…</span>;
  if (!s.covered || !s.split) return <span style={{ fontSize: 13, color: "#5E5A52" }}>No review text in this version: it was collected before reviews were stored. Re-run the retrieval to get them.</span>;
  const sp = s.split;
  const others = (s.langs || []).filter((l) => l.code !== "ja" && !l.code.startsWith("en"));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5, maxWidth: 980 }}>
        Of {fmt(sp.n)} reviews sampled from {fmt(s.covered)} merchants, <b>{pct(sp.ja_pct)} are in Japanese</b>, {pct(sp.en_pct)} in English
        and {pct(sp.other_pct)} in other languages. {fmt(s.foreign_merchants)} merchants ({pct((100 * (s.foreign_merchants || 0)) / s.covered, 0)}) have at least one review by a visitor.
      </p>

      <div style={{ display: "flex", height: 14, gap: 1 }}>
        {GROUPS.map(([k, l]) => sp[k] ? <span key={k} title={`${l}: ${fmt(sp[k])}`} style={{ width: `${sp[`${k}_pct`]}%`, minWidth: 3, background: C[k] }} /> : null)}
      </div>

      <div className="web-tiles">
        {GROUPS.map(([k, l]) => (
          <div key={k} className="web-tile" style={{ minHeight: 0 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}><span style={{ width: 9, height: 9, background: C[k] }} />{l}</span>
            <span style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span className="m" style={{ fontSize: 24, letterSpacing: "-0.02em" }}>{fmt(sp[k])}</span>
              <span className="m" style={{ fontSize: 12, color: "#5E5A52" }}>{pct(sp[`${k}_pct`])}</span>
            </span>
            {k === "other" && others.length > 0 && (
              <span className="m" style={{ fontSize: 10, color: "#8A8478", lineHeight: 1.5 }}>{others.slice(0, 5).map((o) => `${o.name} ${fmt(o.n)}`).join(" · ")}</span>
            )}
          </div>
        ))}
        <div className="web-tile" style={{ minHeight: 0 }}>
          <span style={{ fontSize: 12 }}>Full detail</span>
          <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.4 }}>Summary with top 20s, by area and segment, visitor magnets on the call list; every merchant; every sampled review; live pivots.</span>
          <span style={{ marginTop: "auto" }}><SheetButton path={`/api/versions/${versionId}/sheets/reviews`} primary /></span>
        </div>
      </div>

      <TopList versionId={versionId} areas={s.areas || []} />

      {(s.by_area || []).length > 1 && (
        <div style={{ overflowX: "auto" }}>
          <table className="rv-table">
            <thead><tr><th>Area</th><th className="r">Merchants</th><th className="r">Sampled reviews</th><th className="r">Japanese</th><th className="r">English</th><th className="r">Other</th><th className="r">With a visitor review</th></tr></thead>
            <tbody>
              {s.by_area!.map((a) => (
                <tr key={a.key}><td>{a.key}</td><td className="m r">{fmt(a.merchants)}</td><td className="m r">{fmt(a.n)}</td>
                  <td className="m r">{pct(a.ja_pct)}</td><td className="m r">{pct(a.en_pct)}</td><td className="m r">{pct(a.other_pct)}</td>
                  <td className="m r">{pct(a.foreign_pct, 0)} <span className="rv-of">{fmt(a.foreign_merchants)}</span></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.5, maxWidth: 980 }}>
        Google returns up to 5 "most relevant" reviews per merchant, not all of them. Japanese / English / Other count those; Est. scales the sample to the
        merchant's total reviews. We ask Google in Japanese and it favours reviews in that language, so the English and other shares are a floor.
      </span>
    </div>
  );
}

// How the top list can be ranked; the bold column in the table is the one ranked on
const RANKS: { k: string; l: string; col: string }[] = [
  { k: "ja", l: "Japanese reviews (of the 5 sampled)", col: "ja" },
  { k: "en", l: "English reviews (of the 5 sampled)", col: "en" },
  { k: "est_ja", l: "Est. Japanese reviews", col: "est_ja" },
  { k: "est_en", l: "Est. English reviews", col: "est_en" },
  { k: "share_en", l: "English share of the sample", col: "en" },
  { k: "reviews", l: "Total reviews", col: "reviews" },
  { k: "rating", l: "Rating", col: "rating" },
];
const MINS = [0, 50, 100, 500, 1000];

/** Top 20 merchants, ranked by any review measure, with a minimum review count, an area and a call-list filter. */
function TopList({ versionId, areas }: { versionId: number; areas: string[] }) {
  const [by, setBy] = useState("est_ja");
  const [min, setMin] = useState(0);
  const [minText, setMinText] = useState("0");
  const [area, setArea] = useState("all");
  const [calls, setCalls] = useState(false);
  const [res, setRes] = useState<{ rows: Top[]; total: number } | null>(null);
  const [busy, setBusy] = useState(false);

  // Typing a minimum waits a moment before re-ranking
  useEffect(() => {
    const t = setTimeout(() => setMin(Math.max(0, Number(minText) || 0)), 350);
    return () => clearTimeout(t);
  }, [minText]);
  useEffect(() => {
    let live = true;
    setBusy(true);
    const q = new URLSearchParams({ by, min_reviews: String(min), area, callable_only: String(calls), n: "20" });
    api<{ rows: Top[]; total: number }>(`/api/versions/${versionId}/reviews/top?${q}`)
      .then((r) => live && setRes(r)).catch(() => live && setRes({ rows: [], total: 0 })).finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [versionId, by, min, area, calls]);

  const col = RANKS.find((r) => r.k === by)!.col;
  const b = (c: string) => ({ fontWeight: col === c ? 600 : 400 });
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <span className="lbl">Top 20 · by {RANKS.find((r) => r.k === by)!.l.toLowerCase()}</span>
        <span className="m" style={{ fontSize: 11, color: "#5E5A52" }} aria-live="polite">
          {busy ? "Ranking…" : res ? `${fmt(res.total)} merchants match${res.total > 20 ? " · showing 20" : ""}` : ""}
        </span>
      </div>
      <div className="rv-controls">
        <label className="wf-field">
          <span className="lbl">Rank by</span>
          <select className="in" value={by} onChange={(e) => setBy(e.target.value)}>
            {RANKS.map((r) => <option key={r.k} value={r.k}>{r.l}</option>)}
          </select>
        </label>
        <label className="wf-field">
          <span className="lbl">Min. total reviews</span>
          <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <input className="in m" type="number" min={0} value={minText} onChange={(e) => setMinText(e.target.value)} style={{ width: 96 }} />
            {MINS.map((x) => <button key={x} className="chip" aria-pressed={min === x && Number(minText) === x} onClick={(e) => { e.preventDefault(); setMinText(String(x)); setMin(x); }}>{x ? `${fmt(x)}+` : "Any"}</button>)}
          </span>
        </label>
        <label className="wf-field">
          <span className="lbl">Area</span>
          <select className="in" value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="all">All areas</option>
            {areas.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, alignSelf: "flex-end", minHeight: 34 }}>
          <input type="checkbox" checked={calls} onChange={(e) => setCalls(e.target.checked)} />On the call list only
        </label>
      </div>
      <div style={{ overflowX: "auto", opacity: busy ? 0.55 : 1, transition: "opacity .15s" }}>
        <table className="rv-table">
          <thead><tr><th>#</th><th>Merchant</th><th>Area</th><th className="r">Rating</th><th className="r">Reviews</th><th className="r">Japanese</th><th className="r">English</th><th className="r">Other</th><th className="r">Est. Japanese</th><th className="r">Est. English</th></tr></thead>
          <tbody>
            {(res?.rows || []).map((r, i) => (
              <tr key={r.place_id}>
                <td className="m">{i + 1}</td>
                <td>{r.maps_uri ? <a href={r.maps_uri} target="_blank" rel="noreferrer">{r.name}</a> : r.name}<span style={{ display: "block", fontSize: 10, color: "#8A8478" }}>{r.segment}{r.callable ? " · on the call list" : ""}</span></td>
                <td>{r.area}</td>
                <td className="m r" style={b("rating")}>{r.rating == null ? "—" : r.rating.toFixed(1)}</td>
                <td className="m r" style={b("reviews")}>{fmt(r.reviews)}</td>
                <td className="m r" style={b("ja")}>{r.ja}<span className="rv-of">/{r.sample}</span></td>
                <td className="m r" style={{ ...b("en"), color: r.en ? C.en : undefined }}>{r.en}<span className="rv-of">/{r.sample}</span></td>
                <td className="m r" title={r.other_langs}>{r.other}<span className="rv-of">/{r.sample}</span></td>
                <td className="m r" style={b("est_ja")}>{fmt(r.est_ja)}</td>
                <td className="m r" style={b("est_en")}>{fmt(r.est_en)}</td>
              </tr>
            ))}
            {res && !res.rows.length && <tr><td colSpan={10} style={{ color: "#5E5A52", padding: "14px 0" }}>No merchant matches. Lower the minimum or pick another area.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
