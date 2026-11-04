import { useMemo } from "react";
import type { Points } from "../../components/PlaceMap";
import { fmt, pct } from "../../lib/format";
import { WEB_KINDS, webKind } from "../../lib/web";
import type { ExplorerView } from "./MapExplorer";
import { Profile } from "./types";

type Row = Record<string, any>;
// What each kind of link means for reaching the merchant
const MEANS: Record<string, string> = {
  own: "Their own site, incl. pages on Wix, gorp.jp, owst.jp. A direct line to the owner.",
  group: "A chain, operator or venue site (hotel, department store). Decisions sit at head office.",
  social: "Instagram, X, Facebook, LINE. Direct and informal: DM the owner.",
  booking: "Only a reservation page (TableCheck, Ikyu). A rented channel.",
  aggregator: "Only a Tabelog, Hot Pepper or Gurunavi listing. No channel of their own.",
  none: "No link at all. Phone or walk in.",
};

/** How merchants show up online: the split, what each kind means for sales, the top sites and the split by area. */
export function Websites({ p, points, onPick }: { p: Profile; points: Points | null; onPick: (v: ExplorerView) => void }) {
  const rows = useMemo<Row[]>(() => (points ? points.rows.map((r) => Object.fromEntries(points.cols.map((c, i) => [c, r[i]])) as Row) : [])
    .filter((r) => r.fnb !== "no"), [points]);
  const areas: string[] = (p.areas || []).filter((a: Row) => a.selected ?? a.code !== "outside").map((a: Row) => a.en);
  const count = (rs: Row[]) => Object.fromEntries(WEB_KINDS.map(([k]) => [k, rs.filter((r) => webKind(r) === k).length]));
  const all = useMemo(() => count(rows), [rows]);
  const byArea = useMemo(() => areas.map((a) => {
    const rs = rows.filter((r) => (r.ward_en ?? r.area_en) === a);
    return { a, n: rs.length, c: count(rs) };
  }), [rows, areas.join()]);
  const hosts: Record<string, { host: string; n: number }[]> = Object.fromEntries((p.contact?.web_kinds || []).map((k: Row) => [k.k, k.hosts || []]));

  if (!points) return <span style={{ fontSize: 12, color: "#5E5A52" }}>Loading merchants…</span>;
  const n = Math.max(1, rows.length);
  const share = (k: string, c = all, d = n) => (100 * c[k]) / Math.max(1, d);
  const insta = rows.filter((r) => r.web && /instagram\.com/i.test(r.web)).length;
  const rented = all.booking + all.aggregator;
  // Area with the most and fewest merchants on a channel of their own
  const own = byArea.filter((x) => x.n >= 50).map((x) => ({ ...x, s: (100 * (x.c.own + x.c.social)) / x.n })).sort((a, b) => b.s - a.s);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5, maxWidth: 980 }}>
        {pct(100 - share("none"), 0)} of merchants list a website, but only <b>{pct(share("own"), 0)} run their own</b>.{" "}
        {pct(share("social"), 0)} rely on social media ({fmt(insta)} on Instagram), {pct(share("group"), 0)} sit on a chain or venue site that
        reaches head office, and {pct((100 * rented) / n, 0)} only appear on booking or gourmet portals.
        {own.length > 1 && own[0].s - own[own.length - 1].s >= 10 && <> {own[0].a} has the most merchants on a channel of their own ({pct(own[0].s, 0)}); {own[own.length - 1].a} the fewest ({pct(own[own.length - 1].s, 0)}).</>}
      </p>

      <div style={{ display: "flex", height: 14, gap: 1 }}>
        {WEB_KINDS.map(([k, l, c]) => all[k] ? <span key={k} title={`${l}: ${fmt(all[k])}`} style={{ width: `${share(k)}%`, background: c }} /> : null)}
      </div>

      <div className="web-tiles">
        {WEB_KINDS.map(([k, l, c]) => (
          <button key={k} className="web-tile" onClick={() => onPick({ area: "all", web: k })} title="Show these merchants on the map">
            <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}><span style={{ width: 9, height: 9, background: c }} />{l}</span>
            <span style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span className="m" style={{ fontSize: 24, letterSpacing: "-0.02em" }}>{fmt(all[k])}</span>
              <span className="m" style={{ fontSize: 12, color: "#5E5A52" }}>{pct(share(k), 0)}</span>
            </span>
            <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.4 }}>{MEANS[k]}</span>
            {(hosts[k] || []).length > 0 && (
              <span className="m" style={{ fontSize: 10, color: "#8A8478", lineHeight: 1.5 }}>
                {hosts[k].slice(0, k === "group" ? 4 : 3).map((h) => `${h.host.replace(/^(store|stores|shop|map|maps|tenpo)\./, "")} ${fmt(h.n)}`).join(" · ")}
              </span>
            )}
            <span style={{ fontSize: 11, color: "#C8442B", marginTop: "auto" }}>Show on map →</span>
          </button>
        ))}
      </div>

      {byArea.length > 1 && (
        <div style={{ overflowX: "auto" }}>
          <div style={{ minWidth: 760 }}>
            <div className="m web-area" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
              <span>AREA</span><span>MERCHANTS</span>
              {WEB_KINDS.map(([k, l, c]) => <span key={k} style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><span style={{ width: 8, height: 8, background: c }} />{l.toUpperCase()}</span>)}
            </div>
            {byArea.map((x) => (
              <div key={x.a} className="web-area" style={{ fontSize: 12, padding: "3px 0", borderBottom: "1px solid #E2DDD1", alignItems: "center" }}>
                <span>{x.a}</span><span className="m">{fmt(x.n)}</span>
                {WEB_KINDS.map(([k]) => {
                  const s = share(k, x.c, x.n), base = share(k);
                  return (
                    <button key={k} className="slice-cell" disabled={!x.c[k]} onClick={() => onPick({ area: x.a, web: k })} title={`${fmt(x.c[k])} merchants · show on map`}>
                      <span className="m" style={{ color: s - base >= 5 ? "#A8371F" : undefined, fontWeight: s - base >= 5 ? 600 : 400 }}>{pct(s, 0)}</span>
                      <span className="m" style={{ fontSize: 10, color: "#8A8478" }}>{fmt(x.c[k])}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
          <span style={{ fontSize: 11, color: "#5E5A52" }}>Red = at least 5 points above the all-area share. Click any number to see those merchants on the map.</span>
        </div>
      )}
    </div>
  );
}
