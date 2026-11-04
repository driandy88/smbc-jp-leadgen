import { latLngToCell } from "h3-js";
import { useEffect, useMemo, useState } from "react";
import { PlaceMap, Points } from "../../components/PlaceMap";
import { fmt, pct } from "../../lib/format";
import { WEB_LABEL, webKind } from "../../lib/web";

type Row = Record<string, any>;
export type HotHexes = { top: string; min: number; pool: number; hexes: number; share: number; cells?: { h: string; n: number }[] };

const RES = 9; // the backend's AREA_HEX_RES
const PAY: Record<string, string> = { cash: "Cash only", none: "No payment info", card: "Card", nfc: "Card + NFC / IC" };
const mode = (xs: string[]) => [...xs.reduce((m, x) => m.set(x, (m.get(x) || 0) + 1), new Map<string, number>())].sort((a, b) => b[1] - a[1])[0]?.[0];

/** The hot hexes of one area: pick a hex to see where it is, its merchants on the map and as a list. */
export function HexDialog({ area, hot, hexKm2, points, onClose }: { area: string; hot: HotHexes; hexKm2: number; points: Points; onClose: () => void }) {
  const cells = hot.cells || [];
  const [cell, setCell] = useState(cells[0]?.h ?? null);

  // Merchants of every hot hex, with each hex's own stats for the list
  const byCell = useMemo(() => {
    const want = new Set(cells.map((c) => c.h));
    const m = new Map<string, Row[]>();
    for (const r of points.rows) {
      const o = Object.fromEntries(points.cols.map((c, i) => [c, r[i]])) as Row;
      if (o.lat == null) continue;
      const h = latLngToCell(o.lat, o.lng, RES);
      if (want.has(h)) m.set(h, [...(m.get(h) || []), o]);
    }
    return m;
  }, [points, cells]);
  const rows = (cell && byCell.get(cell)) || [];
  const sub = useMemo<Points>(() => ({ cols: points.cols, rows: rows.map((o) => points.cols.map((c) => o[c])) }), [rows, points.cols]);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  const stat = (rs: Row[]) => ({
    district: mode(rs.map((r) => r.district).filter(Boolean)) || "—",
    reach: rs.filter((r) => r.phone || r.web).length,
    cash: rs.filter((r) => r.pay === "cash" || r.pay === "none").length,
  });
  const cur = stat(rows);
  const list = [...rows].sort((a, b) => (b.reviews || 0) - (a.reviews || 0));

  return (
    <div role="dialog" aria-modal="true" aria-label={`${area} top ${hot.top}% hexes`} className="overlay" onClick={onClose}>
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: "min(1180px, 100%)", maxHeight: "92vh", overflow: "auto", padding: 18, display: "flex", flexDirection: "column", gap: 14, background: "#F8F6F0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="lbl">{area} · top {hot.top}% hexes</span>
            <span style={{ fontSize: 12, color: "#5E5A52", maxWidth: 760 }}>
              {fmt(hot.hexes)} hexes with <b>{fmt(hot.min)}+ F&B merchants</b> each (≈ {fmt(Math.round(hot.min / hexKm2))}+ per km²), the busiest {hot.top}% of all {fmt(hot.pool)} hexes in the picked areas.
              Together they hold {pct(hot.share, 0)} of {area}'s merchants. Each hex is about {hexKm2} km², a block of roughly 350 m across.
            </span>
          </div>
          <button className="btn2" onClick={onClose} aria-label="Close">Close</button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 300px) minmax(0, 1fr)", gap: 16 }} className="hexdlg-grid">
          <div role="listbox" aria-label="Hexes" style={{ display: "flex", flexDirection: "column", maxHeight: 520, overflow: "auto", borderTop: "1px solid #1E1E1C" }}>
            {cells.map((c, i) => {
              const s = stat(byCell.get(c.h) || []);
              return (
                <button key={c.h} role="option" aria-selected={cell === c.h} className="dd-row" onClick={() => setCell(c.h)}
                  style={{ background: cell === c.h ? "#1E1E1C" : undefined, color: cell === c.h ? "#F3F0E8" : undefined, alignItems: "center" }}>
                  <span style={{ display: "flex", gap: 8, minWidth: 0 }}>
                    <span className="m" style={{ opacity: 0.6, width: 20 }}>{i + 1}</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.district}</span>
                  </span>
                  <span className="m" style={{ fontSize: 12, whiteSpace: "nowrap" }}>{fmt(c.n)} · {fmt(Math.round(c.n / hexKm2))}/km²</span>
                </button>
              );
            })}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 18px", fontSize: 12 }}>
              <span><b className="m">{fmt(rows.length)}</b> F&B merchants</span>
              <span><b className="m">{fmt(Math.round(rows.length / hexKm2))}</b> per km²</span>
              <span><b className="m">{pct((100 * cur.reach) / Math.max(1, rows.length), 0)}</b> reachable</span>
              <span><b className="m">{pct((100 * cur.cash) / Math.max(1, rows.length), 0)}</b> cash-only or no card info</span>
              <span style={{ color: "#5E5A52" }}>{cur.district}</span>
            </div>
            <PlaceMap key={cell ?? ""} points={sub} outline={null} highlight={cell} height={380} />
          </div>
        </div>

        <div style={{ overflowX: "auto" }}>
          <div style={{ minWidth: 760, fontSize: 12 }}>
            <div className="m hexdlg-row" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
              <span>MERCHANT</span><span>TYPE</span><span>★ / REVIEWS</span><span>PAYMENT</span><span>PHONE</span><span>WEBSITE</span>
            </div>
            {list.slice(0, 60).map((r, i) => (
              <div key={i} className="hexdlg-row" style={{ padding: "4px 0", borderBottom: "1px solid #E2DDD1" }}>
                <a className="jp" href={r.maps_uri || undefined} target="_blank" rel="noreferrer" style={{ textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</a>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.type_label}</span>
                <span className="m">{r.rating ?? "—"} · {fmt(r.reviews)}</span>
                <span>{PAY[r.pay] || r.pay}</span>
                <span className="m">{r.phone || <span style={{ color: "#A8371F" }}>—</span>}</span>
                <span>{r.web ? <a href={r.web} target="_blank" rel="noreferrer">{WEB_LABEL[webKind(r)]} ↗</a> : <span style={{ color: "#A8371F" }}>none</span>}</span>
              </div>
            ))}
            {list.length > 60 && <span style={{ fontSize: 11, color: "#5E5A52" }}>Top 60 by reviews of {fmt(list.length)}. Download the full list from the contact table.</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
