import { latLngToCell } from "h3-js";
import { useMemo } from "react";
import type { Points } from "../../components/PlaceMap";
import { fmt, pct } from "../../lib/format";
import { isInstagram, webKind } from "../../lib/web";
import { Profile } from "./types";

type Row = Record<string, any>;
const RES = 9; // the backend's AREA_HEX_RES
const share = (n: number, d: number) => (100 * n) / Math.max(1, d);

// The signals every number below is built from. Call list = operating, cash-only or no card info, has a phone
const op = (r: Row) => r.status === "OPERATIONAL";
const cashish = (r: Row) => r.pay === "cash" || r.pay === "none";
const reach = (r: Row) => !!(r.phone || r.web);
const direct = (r: Row) => !!r.phone || ["own", "social"].includes(webKind(r));
const call = (r: Row) => op(r) && cashish(r) && !!r.phone;

/** Lead potential on one screen, nothing to click: funnel, headline numbers, area scorecard, where to walk,
 * who to pitch, how to reach and the watch-outs. */
export function Summary({ p, points }: { p: Profile; points: Points | null }) {
  const rows = useMemo<Row[]>(() => (points ? points.rows.map((r) => {
    const o = Object.fromEntries(points.cols.map((c, i) => [c, r[i]])) as Row;
    o.area = o.ward_en ?? o.area_en;
    o.cell = o.lat != null ? latLngToCell(o.lat, o.lng, RES) : null;
    return o;
  }) : []).filter((r) => r.fnb !== "no"), [points]);

  if (!points) return <div className="card" style={{ padding: 18, fontSize: 12, color: "#5E5A52" }}>Loading merchants…</div>;

  const picked: Row[] = (p.areas || []).filter((a: Row) => a.selected ?? a.code !== "outside");
  const names = new Set(picked.map((a) => a.en));
  const ops = rows.filter(op);
  const chains = (p.areas || []).reduce((s: number, a: Row) => s + (a.chains || 0), 0);
  const hot10 = picked.reduce((s, a) => s + (a.hex?.hot?.[1]?.hexes || 0), 0);
  const hot10Held = picked.reduce((s, a) => s + (a.hex?.hot?.[1]?.cells || []).reduce((t: number, c: Row) => t + c.n, 0), 0);
  const inPicked = rows.filter((r) => names.has(r.area)).length;

  // A. Funnel, on operating merchants; each step says who drops out on the way to the next
  const fReach = ops.filter(reach), fCash = fReach.filter(cashish), fCall = fCash.filter((r) => !!r.phone);
  const funnel = [
    { l: "Operating F&B merchants", n: ops.length },
    { l: "Reachable by phone or website", n: fReach.length, drop: "no phone or website: walk-in only" },
    { l: "Cash-only or no card info", n: fCash.length, drop: "already take cards" },
    { l: "Call list", n: fCall.length, drop: "no phone listed (website only)", accent: true },
  ];

  // B. Headline tiles
  const tiles = [
    { v: fmt(rows.length), l: "F&B merchants", s: `${picked.length} areas + neighbouring wards`, accent: true },
    { v: pct(share(rows.filter(reach).length, rows.length), 0), l: "reachable", s: "phone or website" },
    { v: pct(share(rows.filter(direct).length, rows.length), 0), l: "reachable directly", s: "phone, own site or social" },
    { v: pct(share(ops.filter(cashish).length, ops.length), 0), l: "cash-only or no card info", s: "of operating merchants" },
    { v: fmt(fCall.length), l: "call list", s: "cash / no card, with a phone", accent: true },
    { v: pct(100 - share(chains, rows.length), 0), l: "independents", s: `${fmt(chains)} chain branches` },
    { v: fmt(ops.filter((r) => r.pay === "cash").length), l: "confirmed cash-only", s: `say "cash only" on Google · ${fmt(fCall.filter((r) => r.pay === "cash").length)} on the call list` },
    { v: hot10 ? fmt(hot10) : "—", l: "dense blocks (top-10% hexes)", s: hot10 ? `hold ${pct(share(hot10Held, inPicked), 0)} of merchants` : "re-run Analyze" },
  ];

  // C. Area scorecard: one row per picked area, plus the neighbouring wards together
  const stat = (rs: Row[]) => {
    const o = rs.filter(op);
    return { n: rs.length, reach: share(rs.filter(reach).length, rs.length), cash: share(o.filter(cashish).length, o.length), call: rs.filter(call).length };
  };
  const areaRows = picked.map((a) => ({ name: a.en, ...stat(rows.filter((r) => r.area === a.en)), km2: a.per_km2 as number | null,
                                        dense: a.hex?.hot?.[1]?.hexes as number | undefined })).sort((a, b) => b.call - a.call);
  const nb = rows.filter((r) => !names.has(r.area));
  const nbRow = nb.length ? stat(nb) : null;
  const callTotal = rows.filter(call).length;
  const maxCall = Math.max(1, ...areaRows.map((a) => a.call));

  // One takeaway: the areas to walk (5+ dense blocks) and the ones to phone (spread out)
  const and = (xs: string[]) => xs.length > 1 ? `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}` : xs[0];
  const walkAreas = areaRows.filter((a) => (a.dense ?? 0) >= 5), phoneAreas = areaRows.filter((a) => a.dense != null && a.dense < 5);
  const takeaway = walkAreas.length && phoneAreas.length
    ? `Walk ${and(walkAreas.map((a) => a.name))}: ${pct(share(walkAreas.reduce((s, a) => s + a.call, 0), callTotal), 0)} of the call list, in ${fmt(walkAreas.reduce((s, a) => s + (a.dense || 0), 0))} dense blocks. Phone ${and(phoneAreas.map((a) => a.name))}: merchants are spread out.`
    : "";

  // D. Where to walk first: neighbourhoods of the picked areas by call list, with their dense blocks
  const denseCells = new Set(picked.flatMap((a) => (a.hex?.hot?.[1]?.cells || []).map((c: Row) => `${a.en}|${c.h}`)));
  const hoods = new Map<string, Row[]>();
  for (const r of rows) if (names.has(r.area) && r.district) hoods.set(r.district, [...(hoods.get(r.district) || []), r]);
  const mostly = (rs: Row[]) => [...rs.reduce<Map<string, number>>((m, r) => m.set(r.area, (m.get(r.area) || 0) + 1), new Map())].sort((a, b) => b[1] - a[1])[0][0];
  const walk = [...hoods].map(([d, rs]) => ({ d, area: mostly(rs), ...stat(rs), dense: new Set(rs.filter((r) => denseCells.has(`${r.area}|${r.cell}`)).map((r) => r.cell)).size }))
    .filter((w) => !w.d.includes("· other")).sort((a, b) => b.call - a.call).slice(0, 5);

  // E. Who to pitch: business segments by call list
  const segs = new Map<string, Row[]>();
  for (const r of rows) segs.set(r.segment, [...(segs.get(r.segment) || []), r]);
  const pitch = [...segs].map(([s, rs]) => ({ s, ...stat(rs) })).sort((a, b) => b.call - a.call).slice(0, 3);

  // F. What the website links really are (Google gives one link per merchant)
  const withWeb = rows.filter((r) => r.web);
  const hostOf = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };
  const on = (r: Row, d: string) => { const h = hostOf(r.web); return h === d || h.endsWith("." + d); };
  const socialRows = withWeb.filter((r) => webKind(r) === "social");
  const links = [
    { k: "own", l: "Their own website", s: "own domain or site-builder page", c: "#1E1E1C" },
    { k: "social", l: "Social media", s: `Instagram ${fmt(socialRows.filter((r) => isInstagram(r.web)).length)} · Facebook ${fmt(socialRows.filter((r) => on(r, "facebook.com")).length)} · X ${fmt(socialRows.filter((r) => on(r, "x.com") || on(r, "twitter.com")).length)} · other ${fmt(socialRows.filter((r) => !["instagram.com", "facebook.com", "x.com", "twitter.com"].some((d) => on(r, d))).length)}`, c: "#3E5A63" },
    { k: "group", l: "Group / chain site", s: "the chain, operator or hotel site, not the shop's own", c: "#6E685C" },
    { k: "aggregator", l: "Gourmet portal listing", s: "Tabelog, Hot Pepper, Gurunavi…", c: "#A39B88" },
    { k: "booking", l: "Booking page", s: "TableCheck, Ikyu, Tabelog booking…", c: "#B59A5B" },
  ].map((x) => ({ ...x, n: withWeb.filter((r) => webKind(r) === x.k).length }));

  // G. Watch-outs
  const watch = [
    `${pct(share(ops.filter((r) => r.pay === "none").length, ops.length), 0)} of operating merchants state no payment method on Google: confirm cash vs card on the call.`,
    `${pct(share(chains, rows.length), 0)} are chain branches (${fmt(chains)}); their payment provider is usually chosen at head office.`,
    ...(nb.length ? [`${fmt(nb.length)} merchants sit in neighbouring wards that were only searched along the border, so those counts are partial.`] : []),
  ];

  return (
    <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 22 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <span className="lbl">Lead potential · the numbers that matter</span>
        <span className="m" style={{ fontSize: 11, color: "#5E5A52" }}>straight from the data · call list = operating, cash-only or no card info, with a phone</span>
      </div>

      {/* B. Headline tiles */}
      <div className="sum-tiles">
        {tiles.map((t) => (
          <div key={t.l} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="m" style={{ fontSize: 28, letterSpacing: "-0.02em", color: t.accent ? "#C8442B" : undefined }}>{t.v}</span>
            <span style={{ fontSize: 12 }}>{t.l}</span>
            <span style={{ fontSize: 11, color: "#5E5A52" }}>{t.s}</span>
          </div>
        ))}
      </div>

      <div className="sum-two">
        {/* A. Funnel */}
        <SumBlock t="From everyone found to who to call">
          <div style={{ display: "flex", flexDirection: "column", alignItems: "stretch" }}>
            {funnel.map((f, i) => (
              <div key={f.l} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                {i > 0 && (
                  <span style={{ fontSize: 11, color: "#8A8478", padding: "5px 0" }}>
                    ↓ <span className="m" style={{ color: "#A8371F" }}>−{fmt(funnel[i - 1].n - f.n)}</span> {f.drop}
                  </span>
                )}
                <div className="funnel-step" style={{ width: `${Math.max(34, share(f.n, funnel[0].n))}%`, background: f.accent ? "#C8442B" : "#1E1E1C" }}>
                  <span style={{ fontWeight: f.accent ? 600 : 400 }}>{f.l}</span>
                  <span className="m" style={{ fontSize: 17, fontWeight: 600 }}>{fmt(f.n)}</span>
                </div>
                <span className="m" style={{ fontSize: 10, color: "#5E5A52", paddingTop: 3 }}>
                  {pct(share(f.n, funnel[0].n), 0)} of all{i > 0 ? ` · ${pct(share(f.n, funnel[i - 1].n), 0)} of the step above` : ""}
                </span>
              </div>
            ))}
          </div>
          <span style={{ fontSize: 11, color: "#5E5A52" }}>Call list = operating, cash-only or no card info, with a phone. Bar width = share of operating merchants.</span>
        </SumBlock>

        {/* F. What the website links really are */}
        <SumBlock t="What their website link really is" meta={`${fmt(withWeb.length)} of ${fmt(rows.length)} have a link`}>
          <div style={{ display: "flex", height: 12, gap: 1 }}>
            {links.map((x) => x.n ? <span key={x.k} title={`${x.l}: ${fmt(x.n)}`} style={{ width: `${share(x.n, withWeb.length)}%`, background: x.c }} /> : null)}
          </div>
          {links.map((x) => (
            <div key={x.k} style={{ display: "grid", gridTemplateColumns: "12px minmax(0, 1fr) 64px 40px", gap: 8, alignItems: "baseline", fontSize: 13 }}>
              <span style={{ width: 9, height: 9, background: x.c, alignSelf: "center" }} />
              <span>{x.l} <span style={{ fontSize: 11, color: "#5E5A52" }}>· {x.s}</span></span>
              <span className="m" style={{ textAlign: "right" }}>{fmt(x.n)}</span>
              <span className="m" style={{ textAlign: "right", fontSize: 11, color: "#5E5A52" }}>{pct(share(x.n, withWeb.length), 0)}</span>
            </div>
          ))}
          <span style={{ fontSize: 12, lineHeight: 1.45 }}>
            Only <b>{fmt(links[0].n)}</b> merchants ({pct(share(links[0].n, rows.length), 0)} of all) have a real website of their own. {fmt(rows.length - withWeb.length)} have no link at all.
          </span>
        </SumBlock>
      </div>

      {/* G. Watch-outs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(260px, 100%), 1fr))", gap: "8px 24px", borderTop: "1px solid #E2DDD1", borderBottom: "1px solid #E2DDD1", padding: "10px 0" }}>
        <span className="lbl" style={{ color: "#5E5A52", gridColumn: "1 / -1" }}>Watch-outs</span>
        {watch.map((w) => <span key={w} style={{ fontSize: 12, lineHeight: 1.45, borderLeft: "2px solid #C8442B", paddingLeft: 8 }}>{w}</span>)}
      </div>

      {/* C. Area scorecard */}
      <SumBlock t="Areas">
        <div style={{ overflowX: "auto" }}>
          <div style={{ minWidth: 820, fontSize: 13 }}>
            <div className="sum-area" style={{ borderBottom: "1px solid #1E1E1C", padding: "4px 0", alignItems: "end" }}>
              {[["AREA", ""], ["MERCHANTS", "F&B found"], ["PER KM²", "how packed"], ["DENSE BLOCKS", "350 m blocks, 120+ each"],
                ["REACHABLE", "phone or website"], ["CASH / NO CARD", "of operating"], ["CALL LIST", "cash / no card, with a phone"]].map(([h, sub]) => (
                <span key={h} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <span className="m" style={{ fontSize: 10, color: "#1E1E1C" }}>{h}</span>
                  <span style={{ fontSize: 10, color: "#8A8478" }}>{sub}</span>
                </span>
              ))}
            </div>
            {areaRows.map((a) => (
              <div key={a.name} className="sum-area" style={{ padding: "8px 0", borderBottom: "1px solid #E2DDD1" }}>
                <span className="serif" style={{ fontSize: 18 }}>{a.name}</span>
                <span className="m">{fmt(a.n)}</span>
                <span className="m">{a.km2 ? fmt(Math.round(a.km2)) : "—"}</span>
                <span className="m">{a.dense != null ? fmt(a.dense) : "—"}</span>
                <span className="m">{pct(a.reach, 0)}</span>
                <span className="m">{pct(a.cash, 0)}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ height: 10, width: `${(70 * a.call) / maxCall}%`, background: "#C8442B" }} />
                  <span className="m" style={{ fontWeight: 600 }}>{fmt(a.call)}</span>
                </span>
              </div>
            ))}
            {nbRow && (
              <div className="sum-area" style={{ padding: "6px 0", borderBottom: "1px solid #E2DDD1", color: "#5E5A52", fontSize: 12 }}>
                <span style={{ fontStyle: "italic" }}>Neighbouring wards (partly covered)</span>
                <span className="m">{fmt(nbRow.n)}</span><span>—</span><span>—</span>
                <span className="m">{pct(nbRow.reach, 0)}</span><span className="m">{pct(nbRow.cash, 0)}</span><span className="m">{fmt(nbRow.call)}</span>
              </div>
            )}
          </div>
        </div>
        {takeaway && <span style={{ fontSize: 14, lineHeight: 1.5 }}>{takeaway}</span>}
      </SumBlock>

      <div className="sum-two">
        {/* D. Where to walk first */}
        <SumBlock t="Where to walk first · neighbourhoods by call list">
          <MiniTable head={["NEIGHBOURHOOD", "MERCHANTS", "DENSE BLOCKS", "CALL LIST"]}
            rows={walk.map((w, i) => [<span key="n"><span className="m" style={{ color: "#8A8478", marginRight: 6 }}>{i + 1}</span>{w.d} <span style={{ fontSize: 11, color: "#5E5A52" }}>· {w.area}</span></span>,
              fmt(w.n), fmt(w.dense), <b key="c">{fmt(w.call)}</b>])} />
        </SumBlock>

        {/* E. Who to pitch */}
        <SumBlock t="Who to pitch · segments by call list">
          <MiniTable head={["SEGMENT", "MERCHANTS", "CALL LIST", "SHARE OF LIST"]}
            rows={pitch.map((x) => [x.s, fmt(x.n), <b key="c">{fmt(x.call)}</b>, pct(share(x.call, callTotal), 0)])} />
        </SumBlock>
      </div>
    </div>
  );
}

const SumBlock = ({ t, meta, children }: { t: string; meta?: string; children: React.ReactNode }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, borderBottom: "1px solid #1E1E1C", paddingBottom: 6 }}>
      <span className="lbl" style={{ color: "#1E1E1C" }}>{t}</span>{meta && <span style={{ fontSize: 11, color: "#8A8478" }}>{meta}</span>}
    </div>
    {children}
  </div>
);

function MiniTable({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", fontSize: 13 }}>
      <div className="m sum-mini" style={{ fontSize: 10, color: "#5E5A52", paddingBottom: 4 }}>{head.map((h) => <span key={h}>{h}</span>)}</div>
      {rows.map((r, i) => (
        <div key={i} className="sum-mini" style={{ padding: "5px 0", borderTop: "1px solid #E2DDD1" }}>
          {r.map((c, j) => <span key={j} className={j ? "m" : undefined} style={j ? undefined : { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c}</span>)}
        </div>
      ))}
    </div>
  );
}
