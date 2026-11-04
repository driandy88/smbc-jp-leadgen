import { latLngToCell } from "h3-js";
import { useMemo } from "react";
import type { Points } from "../../components/PlaceMap";
import { fmt, pct } from "../../lib/format";
import { webKind } from "../../lib/web";
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

  // A. Funnel, on operating merchants
  const fReach = ops.filter(reach), fCash = fReach.filter(cashish), fCall = fCash.filter((r) => !!r.phone);
  const funnel = [
    { l: "F&B merchants found", n: rows.length },
    { l: "Operating today", n: ops.length },
    { l: "Reachable by phone or website", n: fReach.length },
    { l: "…and cash-only or no card info", n: fCash.length, note: "the payment opportunity" },
    { l: "…and list a phone: the call list", n: fCall.length, accent: true },
  ];

  // B. Headline tiles
  const tiles = [
    { v: fmt(rows.length), l: "F&B merchants", s: `${picked.length} areas + neighbouring wards`, accent: true },
    { v: pct(share(rows.filter(reach).length, rows.length), 0), l: "reachable", s: "phone or website" },
    { v: pct(share(rows.filter(direct).length, rows.length), 0), l: "reachable directly", s: "phone, own site or social" },
    { v: pct(share(ops.filter(cashish).length, ops.length), 0), l: "cash-only or no card info", s: "of operating merchants" },
    { v: fmt(fCall.length), l: "call list", s: "cash / no card, with a phone", accent: true },
    { v: pct(100 - share(chains, rows.length), 0), l: "independents", s: `${fmt(chains)} chain branches` },
    { v: fmt(rows.filter((r) => r.web && /instagram\.com/i.test(r.web)).length), l: "on Instagram", s: "Instagram is their website" },
    { v: hot10 ? fmt(hot10) : "—", l: "dense blocks (top-10% hexes)", s: hot10 ? `hold ${pct(share(hot10Held, inPicked), 0)} of merchants` : "re-run Analyze" },
  ];

  // C. Area scorecard: one row per picked area, plus the neighbouring wards together
  const stat = (rs: Row[]) => {
    const o = rs.filter(op);
    return { n: rs.length, reach: share(rs.filter(reach).length, rs.length), cash: share(o.filter(cashish).length, o.length),
             call: rs.filter(call).length, ownSocial: share(rs.filter((r) => ["own", "social"].includes(webKind(r))).length, rs.length) };
  };
  const areaRows = picked.map((a) => {
    const s = stat(rows.filter((r) => r.area === a.en));
    const h = a.hex;
    return { name: a.en, ...s, km2: a.per_km2 as number | null, hexes: h?.hexes as number | undefined, half: h?.cover?.["50"] as number | undefined,
             top10: h?.hot?.[1]?.hexes as number | undefined, median: h?.median_active as number | undefined, indie: 100 - share(a.chains || 0, a.places) };
  }).sort((a, b) => b.call - a.call);
  const nb = rows.filter((r) => !names.has(r.area));
  const nbChains = (p.areas || []).filter((a: Row) => !names.has(a.en)).reduce((s: number, a: Row) => s + (a.chains || 0), 0);
  const nbRow = nb.length ? { name: "Neighbouring wards (partly covered)", ...stat(nb), indie: 100 - share(nbChains, nb.length) } : null;

  // Plain read of the scorecard: where the call list clusters, and where it is spread thin
  const callTotal = rows.filter(call).length;
  const dense = areaRows.filter((a) => (a.top10 ?? 0) >= 5);
  const thin = areaRows.filter((a) => a.top10 != null && a.top10 <= 2);
  const and = (xs: string[]) => xs.length > 1 ? `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}` : xs[0];
  const reads: string[] = [];
  if (dense.length) reads.push(`${and(dense.map((a) => a.name))} hold ${pct(share(dense.reduce((s, a) => s + a.call, 0), callTotal), 0)} of the call list `
    + `(${fmt(dense.reduce((s, a) => s + a.call, 0))}), packed into ${fmt(dense.reduce((s, a) => s + (a.top10 || 0), 0))} dense blocks: walk them.`);
  if (thin.length) reads.push(`${and(thin.map((a) => a.name))} ${thin.length > 1 ? "have" : "has"} ${fmt(thin.reduce((s, a) => s + (a.top10 || 0), 0))} dense blocks `
    + `between them and about ${fmt(Math.round(thin.reduce((s, a) => s + (a.median || 0), 0) / thin.length))} merchants per block: phone them rather than walk.`);

  // D. Where to walk first: the busiest blocks of the picked areas
  const cells = new Map<string, Row[]>();
  for (const r of rows) if (r.cell && names.has(r.area)) cells.set(`${r.area}|${r.cell}`, [...(cells.get(`${r.area}|${r.cell}`) || []), r]);
  const walk = [...cells.values()].sort((a, b) => b.length - a.length).slice(0, 5).map((rs) => {
    const ds = rs.map((r) => r.district).filter(Boolean);
    const district = [...ds.reduce((m, d) => m.set(d, (m.get(d) || 0) + 1), new Map<string, number>())].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—";
    return { district, area: rs[0].area, ...stat(rs) };
  });

  // E. Who to pitch: business segments by call list
  const segs = new Map<string, Row[]>();
  for (const r of rows) segs.set(r.segment, [...(segs.get(r.segment) || []), r]);
  const pitch = [...segs].map(([s, rs]) => ({ s, ...stat(rs) })).sort((a, b) => b.call - a.call).slice(0, 3);

  // F. How to reach: each merchant in its best channel
  const channel = (r: Row) => direct(r) ? "direct" : webKind(r) === "group" ? "group" : r.web ? "listing" : "none";
  const ch = [
    { k: "direct", l: "Directly", s: "phone, own site or social", c: "#1E1E1C" },
    { k: "group", l: "Only via head office", s: "chain or venue site, no phone", c: "#6E685C" },
    { k: "listing", l: "Only via a listing", s: "booking or gourmet portal, no phone", c: "#A39B88" },
    { k: "none", l: "Walk-in only", s: "no phone, no website", c: "#C8442B" },
  ].map((x) => ({ ...x, n: rows.filter((r) => channel(r) === x.k).length }));

  // G. Watch-outs
  const watch = [
    `${pct(share(ops.filter((r) => r.pay === "none").length, ops.length), 0)} of operating merchants state no payment method on Google: confirm cash vs card on the call.`,
    `${pct(share(chains, rows.length), 0)} are chain branches (${fmt(chains)}); their payment provider is usually chosen at head office.`,
    ...(nb.length ? [`${fmt(nb.length)} merchants sit in neighbouring wards that were only searched along the border, so those counts are partial.`] : []),
  ];

  const best = (k: "n" | "km2" | "reach" | "cash" | "call" | "ownSocial" | "indie" | "top10") => Math.max(...areaRows.map((a) => (a[k] as number) ?? -1));
  const bestHalf = Math.min(...areaRows.filter((a) => a.half && a.hexes).map((a) => a.half! / a.hexes!));
  const hi = (on: boolean) => (on ? { color: "#C8442B", fontWeight: 600 } : undefined);

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
          {funnel.map((f) => (
            <div key={f.l} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 70px 44px", gap: 10, alignItems: "center", fontSize: 13 }}>
              <span style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <span style={{ fontWeight: f.accent ? 600 : 400 }}>{f.l}{f.note && <span style={{ color: "#5E5A52", fontWeight: 400 }}> · {f.note}</span>}</span>
                <span style={{ height: 10, width: `${share(f.n, rows.length)}%`, background: f.accent ? "#C8442B" : "#1E1E1C" }} />
              </span>
              <span className="m" style={{ textAlign: "right", fontWeight: f.accent ? 600 : 400, color: f.accent ? "#C8442B" : undefined }}>{fmt(f.n)}</span>
              <span className="m" style={{ textAlign: "right", fontSize: 11, color: "#5E5A52" }}>{pct(share(f.n, rows.length), 0)}</span>
            </div>
          ))}
          <span style={{ fontSize: 11, color: "#5E5A52" }}>Each step is a subset of the one above; % = share of all merchants found. {fmt(ops.length - fReach.length)} operating merchants have no phone or website: field visits only.</span>
        </SumBlock>

        {/* F. How to reach */}
        <SumBlock t="How to reach them">
          <div style={{ display: "flex", height: 12, gap: 1 }}>
            {ch.map((x) => x.n ? <span key={x.k} title={`${x.l}: ${fmt(x.n)}`} style={{ width: `${share(x.n, rows.length)}%`, background: x.c }} /> : null)}
          </div>
          {ch.map((x) => (
            <div key={x.k} style={{ display: "grid", gridTemplateColumns: "12px minmax(0, 1fr) 64px 40px", gap: 8, alignItems: "baseline", fontSize: 13 }}>
              <span style={{ width: 9, height: 9, background: x.c, alignSelf: "center" }} />
              <span>{x.l} <span style={{ fontSize: 11, color: "#5E5A52" }}>· {x.s}</span></span>
              <span className="m" style={{ textAlign: "right" }}>{fmt(x.n)}</span>
              <span className="m" style={{ textAlign: "right", fontSize: 11, color: "#5E5A52" }}>{pct(share(x.n, rows.length), 0)}</span>
            </div>
          ))}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6, borderTop: "1px solid #E2DDD1", paddingTop: 10 }}>
            <span className="lbl" style={{ color: "#5E5A52" }}>Watch-outs</span>
            {watch.map((w) => <span key={w} style={{ fontSize: 12, lineHeight: 1.45 }}>· {w}</span>)}
          </div>
        </SumBlock>
      </div>

      {/* C. Area scorecard */}
      <SumBlock t="Area scorecard" meta="red = best in column">
        <div style={{ overflowX: "auto" }}>
          <div style={{ minWidth: 1000, fontSize: 12 }}>
            <div className="m sum-area" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
              <span>AREA</span><span>MERCHANTS</span><span>PER KM²</span><span>HEXES</span><span>HALF THE MERCHANTS IN</span><span>DENSE BLOCKS</span>
              <span>REACHABLE</span><span>CASH / NO CARD</span><span>CALL LIST</span><span>OWN SITE + SOCIAL</span><span>INDEPENDENTS</span>
            </div>
            {areaRows.map((a) => (
              <div key={a.name} className="sum-area" style={{ padding: "6px 0", borderBottom: "1px solid #E2DDD1" }}>
                <span className="serif" style={{ fontSize: 16 }}>{a.name}</span>
                <span className="m" style={hi(a.n === best("n"))}>{fmt(a.n)}</span>
                <span className="m" style={hi(a.km2 === best("km2"))}>{a.km2 ? fmt(Math.round(a.km2)) : "—"}</span>
                <span className="m">{a.hexes != null ? fmt(a.hexes) : "—"}</span>
                <span className="m" style={hi(!!a.half && !!a.hexes && a.half / a.hexes === bestHalf)}>{a.half != null ? `${fmt(a.half)} hexes (${pct(share(a.half, a.hexes || 1), 0)})` : "—"}</span>
                <span className="m" style={hi(a.top10 === best("top10"))}>{a.top10 != null ? fmt(a.top10) : "—"}</span>
                <span className="m" style={hi(a.reach === best("reach"))}>{pct(a.reach, 0)}</span>
                <span className="m" style={hi(a.cash === best("cash"))}>{pct(a.cash, 0)}</span>
                <span className="m" style={hi(a.call === best("call"))}>{fmt(a.call)}</span>
                <span className="m" style={hi(a.ownSocial === best("ownSocial"))}>{pct(a.ownSocial, 0)}</span>
                <span className="m" style={hi(a.indie === best("indie"))}>{pct(a.indie, 0)}</span>
              </div>
            ))}
            {nbRow && (
              <div className="sum-area" style={{ padding: "6px 0", borderBottom: "1px solid #E2DDD1", color: "#5E5A52" }}>
                <span style={{ fontStyle: "italic" }}>{nbRow.name}</span>
                <span className="m">{fmt(nbRow.n)}</span><span>—</span><span>—</span><span>—</span><span>—</span>
                <span className="m">{pct(nbRow.reach, 0)}</span><span className="m">{pct(nbRow.cash, 0)}</span><span className="m">{fmt(nbRow.call)}</span>
                <span className="m">{pct(nbRow.ownSocial, 0)}</span><span className="m">{pct(nbRow.indie, 0)}</span>
              </div>
            )}
          </div>
        </div>
        {reads.map((t) => <span key={t} style={{ fontSize: 13, lineHeight: 1.5 }}>{t}</span>)}
        <span style={{ fontSize: 11, color: "#5E5A52" }}>
          Hex = a ~350 m block. Half the merchants in = the fewest blocks holding half the area's merchants (fewer = tighter cluster).
          Dense blocks = top-10% hexes across the picked areas.
        </span>
      </SumBlock>

      <div className="sum-two">
        {/* D. Where to walk first */}
        <SumBlock t="Where to walk first · busiest blocks">
          <MiniTable head={["BLOCK", "MERCHANTS", "CASH / NO CARD", "CALL LIST", "REACHABLE"]}
            rows={walk.map((w, i) => [<span key="n"><span className="m" style={{ color: "#8A8478", marginRight: 6 }}>{i + 1}</span>{w.district} <span style={{ fontSize: 11, color: "#5E5A52" }}>· {w.area}</span></span>,
              fmt(w.n), pct(w.cash, 0), fmt(w.call), pct(w.reach, 0)])} />
        </SumBlock>

        {/* E. Who to pitch */}
        <SumBlock t="Who to pitch · segments by call list">
          <MiniTable head={["SEGMENT", "MERCHANTS", "CASH / NO CARD", "CALL LIST", "SHARE OF LIST"]}
            rows={pitch.map((s) => [s.s, fmt(s.n), pct(s.cash, 0), fmt(s.call), pct(share(s.call, callTotal), 0)])} />
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
