import { cellToBoundary } from "h3-js";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { fmt } from "../lib/format";
import { WEB_KINDS, WEB_LABEL, webKind } from "../lib/web";
import { Outline } from "./HexMap";

/** Columns + row arrays from /points; one row per merchant. */
export type Points = { cols: string[]; rows: unknown[][] };
type Place = {
  lat: number; lng: number; name: string; type_label: string; rating: number | null; reviews: number | null;
  pay: string; fnb: string; area_en: string; ward_en?: string; maps_uri: string | null; address: string; phone: string | null;
  web: string | null; web_kind?: string | null; status: string; segment: string; district: string;
};
/** Densest neighbourhoods from the profile: merchants per km² in a 300 m circle, named by district. */
export type Hotspot = { name: string; ward: string; lat: number; lng: number; density_km2: number; n: number; radius_m: number; reach_pct: number };

export type Mode = "contact" | "web" | "pay";
const SCHEMES: Record<Mode, { label: string; key: (p: Place) => string; keys: [string, string, string][] }> = {
  contact: {
    label: "Contact", key: (p) => (p.phone && p.web ? "both" : p.phone ? "phone" : p.web ? "web" : "none"),
    keys: [["both", "Phone + website", "#1E1E1C"], ["phone", "Phone only", "#6E685C"], ["web", "Website only", "#A39B88"], ["none", "No contact", "#C8442B"]],
  },
  web: { label: "Website type", key: webKind, keys: WEB_KINDS },
  pay: {
    label: "Payment", key: (p) => p.pay,
    keys: [["cash", "Cash only", "#8F2D1B"], ["none", "No payment info", "#D48E78"], ["card", "Card", "#6E685C"], ["nfc", "Card + NFC / IC", "#3E5A63"]],
  },
};
const PAY_LABEL: Record<string, string> = { cash: "Cash only", none: "No payment info", card: "Card", nfc: "Card + NFC / IC" };

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

function popup(p: Place) {
  const link = (href: string | null, text: string) => (href && /^https?:\/\//.test(href) ? `<a href="${esc(href)}" target="_blank" rel="noreferrer">${text}</a>` : "");
  return `<div class="pm-pop">
    <b class="jp">${esc(p.name)}</b>
    <span>${esc(p.type_label)} · ${esc(p.district || p.ward_en || p.area_en)}</span>
    <span class="m">${p.rating != null ? `★${p.rating}` : "unrated"} · ${fmt(p.reviews)} reviews</span>
    <span>${esc(PAY_LABEL[p.pay] || p.pay)}${p.status !== "OPERATIONAL" ? ` · ${esc(p.status.toLowerCase().replace("_", " "))}` : ""}</span>
    ${p.address ? `<span class="jp" style="color:#5E5A52">${esc(p.address)}</span>` : ""}
    <span class="m">${p.phone ? esc(p.phone) : '<span style="color:#A8371F">no phone</span>'}${p.web ? "" : ' · <span style="color:#A8371F">no website</span>'}</span>
    <span style="display:flex;gap:12px">${link(p.maps_uri, "Google Maps ↗")}${link(p.web, `${p.web ? esc(WEB_LABEL[webKind(p)]) : "Website"} ↗`)}</span>
  </div>`;
}

/**
 * Every merchant as a dot over a street basemap, with the densest neighbourhoods circled and named.
 * Basemap: GSI 地理院タイル (pale), free and keyless, so it works on any page.
 */
const DOT_ZOOM = 15;

/** A shaded hex under the dots; clicking it calls onHex. */
export type HexShade = { h: string; color: string; tip: string; opacity?: number };

export function PlaceMap({ points, outline, hotspots, highlight, height = 560, hexes, onHex, fitKey, dim, modes = ["contact", "web", "pay"] }: {
  points: Points | null; outline: Outline | null; res?: number; hotspots?: Hotspot[]; highlight?: string | null; height?: number;
  hexes?: HexShade[]; onHex?: (h: string) => void;
  /** Refit to the merchants only when this changes (e.g. the picked area), not on every filter */
  fitKey?: string;
  /** A hex layer is on: dots only from DOT_ZOOM in, smaller, so the hexes read at a glance */
  dim?: boolean;
  /** Colour-by options to offer */
  modes?: Mode[];
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const dots = useRef<L.LayerGroup | null>(null);
  const shades = useRef<L.LayerGroup | null>(null);
  const onHexRef = useRef(onHex);
  onHexRef.current = onHex;
  const spots = useRef<L.LayerGroup | null>(null);
  const hi = useRef<L.Polygon | null>(null);
  const [mode, setMode] = useState<Mode>("contact");
  const [showSpots, setShowSpots] = useState(true);
  const [zoom, setZoom] = useState(11);

  const places = useMemo<Place[]>(() => {
    if (!points) return [];
    return points.rows.map((r) => Object.fromEntries(points.cols.map((c, i) => [c, r[i]])) as Place);
  }, [points]);
  const shown = places;

  useEffect(() => {
    const m = L.map(el.current!, { preferCanvas: true, zoomControl: true, scrollWheelZoom: false, attributionControl: true });
    L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
      maxZoom: 18, attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noreferrer">地理院タイル</a>',
    }).addTo(m);
    m.setView([34.69, 135.5], 11);
    // Wheel zoom only after the map is clicked, so the page still scrolls past it
    m.on("click", () => m.scrollWheelZoom.enable());
    m.on("mouseout", () => m.scrollWheelZoom.disable());
    m.on("zoomend", () => setZoom(m.getZoom()));
    shades.current = L.layerGroup().addTo(m);
    spots.current = L.layerGroup().addTo(m);
    dots.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m || !outline) return;
    // Bold ward borders, each ward named at its centre, faint so the hexes and dots still read
    const layer = L.geoJSON(outline as unknown as GeoJSON.FeatureCollection, {
      style: { color: "#1E1E1C", weight: 2.6, opacity: 0.85, fill: false, interactive: false },
    }).addTo(m);
    const names = L.layerGroup().addTo(m);
    layer.eachLayer((l) => {
      const f = (l as L.Polygon & { feature?: { properties?: { en?: string } } }).feature;
      if (!f?.properties?.en) return;
      L.marker((l as L.Polygon).getCenter(), {
        icon: L.divIcon({ className: "pm-ward", html: esc(f.properties.en), iconSize: undefined as unknown as L.PointExpression }),
        interactive: false, keyboard: false,
      }).addTo(names);
    });
    return () => { layer.remove(); names.remove(); };
  }, [outline]);

  // Hotspots: the densest neighbourhoods, drawn as circles with their name and density
  useEffect(() => {
    const g = spots.current;
    if (!g) return;
    g.clearLayers();
    if (!showSpots || !hotspots?.length) return;
    const max = Math.max(...hotspots.map((h) => h.density_km2));
    hotspots.forEach((h, i) => {
      L.circle([h.lat, h.lng], { radius: h.radius_m, color: "#C8442B", weight: 1.5, fillColor: "#C8442B", fillOpacity: 0.08 + 0.17 * (h.density_km2 / max), interactive: false }).addTo(g);
      L.marker([h.lat, h.lng], {
        icon: L.divIcon({ className: "pm-spot", html: `<b>${i + 1}</b> ${esc(h.name)}<span>${fmt(h.density_km2)}/km²</span>`, iconSize: undefined as unknown as L.PointExpression }),
        interactive: false, keyboard: false,
      }).addTo(g);
    });
  }, [hotspots, showSpots]);

  useEffect(() => {
    const g = dots.current;
    if (!g) return;
    g.clearLayers();
    const s = SCHEMES[mode];
    const color = Object.fromEntries(s.keys.map(([k, , c]) => [k, c]));
    if (dim && zoom < DOT_ZOOM) return;
    for (const p of shown) {
      L.circleMarker([p.lat, p.lng], {
        radius: dim ? 2.5 : 4, weight: dim ? 0 : 0.8, color: "#F8F6F0", fillColor: color[s.key(p)] || "#8A8478", fillOpacity: dim ? 0.55 : 0.92,
      })
        .bindTooltip(esc(p.name), { direction: "top", offset: [0, -4], className: "pm-tip" })
        .bindPopup(() => popup(p), { maxWidth: 280 })
        .addTo(g);
    }
  }, [shown, mode, dim, zoom >= DOT_ZOOM]);

  // Hex shading under the dots
  useEffect(() => {
    const g = shades.current;
    if (!g) return;
    g.clearLayers();
    for (const x of hexes || []) {
      L.polygon(cellToBoundary(x.h) as [number, number][], { color: "#1E1E1C", weight: 0.4, opacity: 0.5, fillColor: x.color, fillOpacity: x.opacity ?? 0.5 })
        .bindTooltip(x.tip, { sticky: true, className: "pm-tip" })
        .on("click", () => onHexRef.current?.(x.h))
        .addTo(g);
    }
  }, [hexes]);

  // Fit to the merchants once they arrive, when fitKey changes and when a hex is let go (not on every filter)
  const hasPlaces = places.length > 0;
  useEffect(() => {
    if (map.current && hasPlaces && !highlight) map.current.fitBounds(L.latLngBounds(places.map((p) => [p.lat, p.lng])), { padding: [24, 24] });
  }, [hasPlaces, fitKey, highlight]);

  useEffect(() => {
    hi.current?.remove();
    if (!highlight || !map.current) return;
    hi.current = L.polygon(cellToBoundary(highlight) as [number, number][], { color: "#C8442B", weight: 2.4, fill: false, interactive: false }).addTo(map.current);
    map.current.fitBounds(hi.current.getBounds(), { padding: [120, 120], maxZoom: 16 });
  }, [highlight]);

  const counts = useMemo(() => {
    const s = SCHEMES[mode];
    const c: Record<string, number> = {};
    for (const p of shown) c[s.key(p)] = (c[s.key(p)] || 0) + 1;
    return c;
  }, [shown, mode]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", alignItems: "center" }}>
        <div role="radiogroup" aria-label="Colour dots by" className="seg pm-seg">
          {modes.map((k) => (
            <button key={k} role="radio" aria-checked={mode === k} onClick={() => setMode(k)}>{SCHEMES[k].label}</button>
          ))}
        </div>
        {!!hotspots?.length && <button className="tog" aria-pressed={showSpots} onClick={() => setShowSpots(!showSpots)}><span className="trk"><span className="knob" /></span>Hotspots</button>}
        <span className="m" style={{ marginLeft: "auto", fontSize: 11, color: "#5E5A52" }}>{points ? `${fmt(shown.length)} merchants` : "loading…"}</span>
      </div>
      <div ref={el} className="pm-map" style={{ height }} role="region" aria-label="Interactive map of merchants" />
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px", fontSize: 11, color: "#5E5A52", alignItems: "center" }}>
        {SCHEMES[mode].keys.map(([k, l, c]) => (
          <span key={k} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: c }} />{l} <span className="m">{fmt(counts[k] || 0)}</span>
          </span>
        ))}
        <span style={{ marginLeft: "auto" }}>{dim && zoom < DOT_ZOOM ? "Zoom in (or click a hex) to see the merchants as dots" : "Hover a dot for the name, click for details · click the map to zoom with the wheel"}</span>
      </div>
    </div>
  );
}
