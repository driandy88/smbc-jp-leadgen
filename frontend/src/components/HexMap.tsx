import { cellToBoundary } from "h3-js";
import { useMemo } from "react";

type Ring = number[][]; // [lng, lat]
export type Outline = { type: "FeatureCollection"; features: { properties: { code: string; jp: string; en: string }; geometry: { type: string; coordinates: any } }[] };

export type HexLayer = { cells: string[]; fill: string; stroke?: string; opacity?: number; strokeWidth?: number };

type Props = {
  outline?: Outline | null;
  layers: HexLayer[];
  height?: number;
  labels?: boolean;
  labelPx?: number;
  highlight?: { cell: string; text: string } | null;
  ariaLabel: string;
};

function rings(geom: { type: string; coordinates: any }): Ring[] {
  if (geom.type === "Polygon") return geom.coordinates;
  if (geom.type === "MultiPolygon") return geom.coordinates.flat();
  return [];
}

/** Equirectangular projection fitted to the outline (or the cells when there is no outline). */
export function HexMap({ outline, layers, height = 300, labels = true, labelPx = 11, highlight, ariaLabel }: Props) {
  const geo = useMemo(() => {
    const outRings = (outline?.features || []).map((f) => ({ f, rings: rings(f.geometry) }));
    const pts: number[][] = outRings.flatMap((o) => o.rings.flat());
    const cellRings = new Map<string, Ring>();
    for (const l of layers)
      for (const c of l.cells) if (!cellRings.has(c)) cellRings.set(c, cellToBoundary(c, true) as Ring);
    if (!pts.length) for (const r of cellRings.values()) pts.push(...r);
    if (!pts.length) return null;
    let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity];
    for (const [lng, lat] of pts) {
      x0 = Math.min(x0, lng); x1 = Math.max(x1, lng); y0 = Math.min(y0, lat); y1 = Math.max(y1, lat);
    }
    const k = Math.cos(((y0 + y1) / 2) * (Math.PI / 180));
    const S = 1000 / Math.max((x1 - x0) * k, y1 - y0, 1e-6);
    const px = ([lng, lat]: number[]) => `${((lng - x0) * k * S).toFixed(1)} ${((y1 - lat) * S).toFixed(1)}`;
    const path = (r: Ring) => "M" + r.map(px).join(" L") + " Z";
    const w = (x1 - x0) * k * S;
    const h = (y1 - y0) * S;
    const centroid = (r: Ring) => {
      const [sx, sy] = r.reduce(([a, b], [lng, lat]) => [a + lng, b + lat], [0, 0]);
      return px([sx / r.length, sy / r.length]).split(" ").map(Number);
    };
    return {
      vb: `-20 -20 ${w + 40} ${h + 40}`,
      base: outRings.map((o) => o.rings.map(path).join(" ")).join(" "),
      labels: outRings.map((o) => {
        const big = o.rings.reduce((a, b) => (b.length > a.length ? b : a), [] as Ring);
        const [x, y] = centroid(big);
        return { x, y, t: o.f.properties.jp };
      }),
      layers: layers.map((l) => ({ ...l, d: l.cells.map((c) => path(cellRings.get(c)!)).join(" ") })),
      hl: highlight && cellRings.has(highlight.cell) ? { d: path(cellRings.get(highlight.cell)!), at: centroid(cellRings.get(highlight.cell)!), text: highlight.text } : null,
      scale: S,
    };
  }, [outline, layers, highlight]);

  if (!geo) return <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "#8A8478", fontSize: 12 }}>No cells yet</div>;
  // The projection fits the longer side to 1000 units; scale text and strokes to the rendered height
  const sw = 1000 / height;
  return (
    <svg viewBox={geo.vb} style={{ width: "100%", height, display: "block" }} role="img" aria-label={ariaLabel}>
      <path d={geo.base} fill="#EFEBE1" stroke="#C9C2B2" strokeWidth={sw * 0.8} />
      {geo.layers.map((l, i) => (
        <path key={i} d={l.d} fill={l.fill} fillOpacity={l.opacity ?? 1} stroke={l.stroke || "#F3F0E8"} strokeWidth={(l.strokeWidth ?? 0.8) * sw} />
      ))}
      {geo.hl && (
        <>
          <path d={geo.hl.d} fill="none" stroke="#C8442B" strokeWidth={2.2 * sw} />
          <text x={geo.hl.at[0] + 14 * sw} y={geo.hl.at[1]} fontFamily="'IBM Plex Mono', monospace" fontSize={labelPx * sw} fill="#A8371F">{geo.hl.text}</text>
        </>
      )}
      {labels && geo.labels.map((l, i) => (
        <text key={i} x={l.x} y={l.y} textAnchor="middle" fontFamily="'Noto Sans JP', sans-serif" fontSize={labelPx * sw} fill="#1E1E1C" opacity={0.7} style={{ pointerEvents: "none" }}>{l.t}</text>
      ))}
    </svg>
  );
}
