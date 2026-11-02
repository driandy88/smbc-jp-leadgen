import { HexLayer } from "../../components/HexMap";

export const CAT_COLORS = ["#1E1E1C", "#C8442B", "#6E685C", "#A39B88", "#5E7D4A", "#C9C2B2", "#8E9EA3", "#D48E78", "#3E5A63", "#E6E1D5"];
export const DENSITY = ["#E6E1D5", "#C9C2B2", "#A39B88", "#6E685C", "#1E1E1C"];
export const CASH = ["#EFE3DA", "#E2BFAF", "#D48E78", "#C8604A", "#8F2D1B"];
export const PRICE_COLORS = ["#E6E1D5", "#C9C2B2", "#A39B88", "#6E685C", "#1E1E1C", "#F3F0E8"];

/** Bucket cells into colour layers by thresholds, e.g. [10, 25, 45, 80] → 5 layers. */
export function binLayers<T extends { h: string }>(items: T[], value: (x: T) => number, cuts: number[], colors: string[]): HexLayer[] {
  const layers: HexLayer[] = colors.map((c) => ({ cells: [], fill: c }));
  for (const it of items) {
    const v = value(it);
    let i = cuts.findIndex((c) => v < c);
    if (i < 0) i = cuts.length;
    layers[i].cells.push(it.h);
  }
  return layers;
}

/** Quantile cut points so each colour has a similar number of cells. */
export function quantileCuts(values: number[], n = 5): number[] {
  const s = [...values].sort((a, b) => a - b);
  if (!s.length) return [1, 2, 3, 4];
  const cuts = [];
  for (let i = 1; i < n; i++) cuts.push(s[Math.floor((i * s.length) / n)] + 0.001);
  return cuts;
}

export function Legend({ colors, labels, title }: { colors: string[]; labels: string; title: string }) {
  return (
    <div className="m" style={{ display: "flex", alignItems: "center", fontSize: 10, color: "#5E5A52", flexWrap: "wrap", gap: 0 }}>
      <span style={{ marginRight: 8 }}>{title}</span>
      {colors.map((c) => <span key={c} style={{ width: 30, height: 8, background: c, border: c === "#F3F0E8" ? "1px solid #D8D3C7" : undefined }} />)}
      <span style={{ marginLeft: 8 }}>{labels}</span>
    </div>
  );
}

export function VBars({ data, color = "#1E1E1C", height = 160 }: { data: { l: string; v: number; c?: string }[]; color?: string; height?: number }) {
  const max = Math.max(1, ...data.map((d) => d.v));
  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height, borderBottom: "1px solid #1E1E1C" }}>
        {data.map((b) => (
          <div key={b.l} title={`${b.l} · ${b.v}`} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", alignItems: "center", gap: 4, height: "100%" }}>
            <span className="m" style={{ fontSize: 9, color: "#5E5A52" }}>{b.v.toLocaleString()}</span>
            <span style={{ width: "100%", height: `${(100 * b.v) / max}%`, background: b.c || color }} />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 4 }}>{data.map((b) => <span key={b.l} className="m" style={{ flex: 1, textAlign: "center", fontSize: 9, color: "#5E5A52" }}>{b.l}</span>)}</div>
    </>
  );
}
