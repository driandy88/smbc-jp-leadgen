import { useEffect, useState } from "react";
import { api, ApiError } from "../../api";
import { fmt, pct } from "../../lib/format";
import { SheetButton } from "./Websites";

type Split = { ja: number; en: number; other: number; n: number; ja_pct: number; en_pct: number; other_pct: number };
type Top = { place_id: string; name: string; area: string; segment: string; rating: number | null; reviews: number; sample: number;
  ja: number; en: number; other: number; other_langs: string; est_ja: number; est_en: number; maps_uri: string | null; callable: boolean };
type ByRow = Split & { key: string; merchants: number; foreign_merchants: number; foreign_pct: number };
type Summary = { covered: number; merchants: number; sampled?: number; total_reviews?: number; split?: Split;
  langs?: { code: string; name: string; n: number }[]; foreign_merchants?: number; top_ja?: Top[]; top_en?: Top[]; by_area?: ByRow[] };

const C = { ja: "#1E1E1C", en: "#C8442B", other: "#B59A5B" };
const GROUPS: [keyof typeof C, string][] = [["ja", "Japanese"], ["en", "English"], ["other", "Other languages"]];

/** Who reviews the merchants: Japanese locals or visitors. Measured on the up-to-5 reviews Google returns per place. */
export function ReviewLangs({ versionId }: { versionId: number }) {
  const [s, setS] = useState<Summary | null>(null);
  const [err, setErr] = useState("");
  const [rank, setRank] = useState<"ja" | "en">("ja");
  useEffect(() => {
    api<Summary>(`/api/versions/${versionId}/reviews`).then(setS).catch((e) => setErr(e instanceof ApiError ? e.message : "Couldn't load reviews"));
  }, [versionId]);

  if (err) return <span role="alert" style={{ fontSize: 12, color: "#B33A3A" }}>{err}</span>;
  if (!s) return <span style={{ fontSize: 12, color: "#5E5A52" }}>Reading reviews…</span>;
  if (!s.covered || !s.split) return <span style={{ fontSize: 13, color: "#5E5A52" }}>No review text in this version: it was collected before reviews were stored. Re-run the retrieval to get them.</span>;
  const sp = s.split;
  const top = (rank === "ja" ? s.top_ja : s.top_en) || [];
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

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span className="lbl">Top 20 · most {rank === "ja" ? "Japanese" : "English"} reviews (est.)</span>
        <div style={{ display: "flex", gap: 6 }} role="group" aria-label="Rank by">
          {(["ja", "en"] as const).map((k) => (
            <button key={k} className="chip" aria-pressed={rank === k} onClick={() => setRank(k)}>{k === "ja" ? "Japanese" : "English"}</button>
          ))}
        </div>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="rv-table">
          <thead><tr><th>#</th><th>Merchant</th><th>Area</th><th className="r">Rating</th><th className="r">Reviews</th><th className="r">Japanese</th><th className="r">English</th><th className="r">Other</th><th className="r">Est. Japanese</th><th className="r">Est. English</th></tr></thead>
          <tbody>
            {top.map((r, i) => (
              <tr key={r.place_id}>
                <td className="m">{i + 1}</td>
                <td>{r.maps_uri ? <a href={r.maps_uri} target="_blank" rel="noreferrer">{r.name}</a> : r.name}<span style={{ display: "block", fontSize: 10, color: "#8A8478" }}>{r.segment}{r.callable ? " · on the call list" : ""}</span></td>
                <td>{r.area}</td>
                <td className="m r">{r.rating ?? "—"}</td>
                <td className="m r">{fmt(r.reviews)}</td>
                <td className="m r">{r.ja}<span className="rv-of">/{r.sample}</span></td>
                <td className="m r" style={{ color: r.en ? C.en : undefined }}>{r.en}<span className="rv-of">/{r.sample}</span></td>
                <td className="m r" title={r.other_langs}>{r.other}<span className="rv-of">/{r.sample}</span></td>
                <td className="m r" style={{ fontWeight: rank === "ja" ? 600 : 400 }}>{fmt(r.est_ja)}</td>
                <td className="m r" style={{ fontWeight: rank === "en" ? 600 : 400 }}>{fmt(r.est_en)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
