import { useMemo, useState } from "react";
import { api, ApiError, download } from "../../api";
import type { Points } from "../../components/PlaceMap";
import { fmt, pct } from "../../lib/format";
import { WEB_KINDS, webKind } from "../../lib/web";
import { Profile } from "./types";

type Row = Record<string, any>;
// What each kind of link means for reaching the merchant
const MEANS: Record<string, string> = {
  own: "Their own site, incl. pages on Wix, gorp.jp, owst.jp. A direct line to the owner.",
  group: "A chain, operator or venue site (hotel, department store). Decisions sit at head office.",
  social: "Instagram, X, Facebook, LINE. Direct and informal: DM the owner.",
  portal: "Only a booking page or gourmet portal (TableCheck, Tabelog, Hot Pepper). A rented channel.",
  none: "No link at all. Phone or walk in, or let the agent below look for their site.",
};

/**
 * Opens a Google Sheet the backend builds. The tab is opened on click (so the browser doesn't block it as a
 * pop-up) and pointed at the sheet once it's ready.
 */
export function SheetButton({ path, label = "Open in Google Sheets", disabled, primary }: { path: string; label?: string; disabled?: boolean; primary?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const go = async () => {
    setBusy(true);
    setErr("");
    setNote("");
    const tab = window.open("", "_blank");
    tab?.document.write('<p style="font:14px system-ui;color:#5E5A52;padding:24px">Building the Google Sheet…</p>');
    try {
      const r = await api<{ url?: string; xlsx?: string; filename?: string }>(path, { method: "POST" });
      if (r.url) {
        if (tab) tab.location.href = r.url;
        else window.open(r.url, "_blank", "noopener");
      } else if (r.xlsx) {
        // Google Drive won't hold it (no Shared Drive folder yet): the same workbook as an Excel file
        tab?.close();
        await download(r.xlsx, r.filename || "hexline.xlsx");
        setNote("Downloaded as Excel: open it in Google Sheets with File → Import, or drag it into Drive.");
      }
    } catch (e) {
      tab?.close();
      setErr(e instanceof ApiError ? e.message : "Couldn't create the sheet");
    } finally {
      setBusy(false);
    }
  };
  return (
    <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <button className={primary ? "btn" : "btn2"} onClick={go} disabled={busy || disabled} style={{ alignSelf: "flex-start", minHeight: 0, padding: "6px 10px", fontSize: 12 }}>
        {busy ? <><span className="wf-spin" aria-hidden="true" />Building sheet…</> : <>{label} ↗</>}
      </button>
      {err && <span role="alert" style={{ fontSize: 11, color: "#B33A3A", lineHeight: 1.4 }}>{err}</span>}
      {note && <span role="status" style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.4 }}>{note}</span>}
    </span>
  );
}

/** How merchants show up online: the split, what each class means for sales, its top sites, a Google Sheet per class, and the split by area. */
export function Websites({ p, points, versionId }: { p: Profile; points: Points | null; versionId: number }) {
  const rows = useMemo<Row[]>(() => (points ? points.rows.map((r) => Object.fromEntries(points.cols.map((c, i) => [c, r[i]])) as Row) : [])
    .filter((r) => r.fnb !== "no"), [points]);
  const areas: string[] = (p.areas || []).filter((a: Row) => a.selected ?? a.code !== "outside").map((a: Row) => a.en);
  const count = (rs: Row[]) => Object.fromEntries(WEB_KINDS.map(([k]) => [k, rs.filter((r) => webKind(r) === k).length]));
  const all = useMemo(() => count(rows), [rows]);
  const byArea = useMemo(() => areas.map((a) => {
    const rs = rows.filter((r) => (r.ward_en ?? r.area_en) === a);
    return { a, n: rs.length, c: count(rs) };
  }), [rows, areas.join()]);
  // Top sites per class from the analysis; booking + aggregator from older analyses fold into portal
  const hosts = useMemo(() => {
    const out: Record<string, { host: string; n: number }[]> = {};
    for (const k of p.contact?.web_kinds || []) {
      const key = webKind({ web: "x", web_kind: k.k });
      out[key] = [...(out[key] || []), ...(k.hosts || [])].sort((x, y) => y.n - x.n);
    }
    return out;
  }, [p]);
  const callable = (r: Row) => r.status === "OPERATIONAL" && (r.pay === "cash" || r.pay === "none") && !!r.phone;
  const calls = useMemo(() => Object.fromEntries(WEB_KINDS.map(([k]) => [k, rows.filter((r) => webKind(r) === k && callable(r)).length])), [rows]);

  if (!points) return <span style={{ fontSize: 12, color: "#5E5A52" }}>Loading merchants…</span>;
  const n = Math.max(1, rows.length);
  const share = (k: string, c = all, d = n) => (100 * c[k]) / Math.max(1, d);
  const insta = rows.filter((r) => r.web && /instagram\.com/i.test(r.web)).length;
  // Area with the most and fewest merchants on a channel of their own
  const own = byArea.filter((x) => x.n >= 50).map((x) => ({ ...x, s: (100 * (x.c.own + x.c.social)) / x.n })).sort((a, b) => b.s - a.s);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5, maxWidth: 980 }}>
        {pct(100 - share("none"), 0)} of merchants list a website, but only <b>{pct(share("own"), 0)} run their own</b>.{" "}
        {pct(share("social"), 0)} rely on social media ({fmt(insta)} on Instagram), {pct(share("group"), 0)} sit on a chain or venue site that
        reaches head office, and {pct(share("portal"), 0)} only appear on a booking site or gourmet portal.
        {own.length > 1 && own[0].s - own[own.length - 1].s >= 10 && <> {own[0].a} has the most merchants on a channel of their own ({pct(own[0].s, 0)}); {own[own.length - 1].a} the fewest ({pct(own[own.length - 1].s, 0)}).</>}
      </p>

      <div style={{ display: "flex", height: 14, gap: 1 }}>
        {WEB_KINDS.map(([k, l, c]) => all[k] ? <span key={k} title={`${l}: ${fmt(all[k])}`} style={{ width: `${share(k)}%`, background: c }} /> : null)}
      </div>

      <div className="web-tiles">
        {WEB_KINDS.map(([k, l, c]) => (
          <div key={k} className="web-tile">
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
            <span className="m" style={{ fontSize: 11, color: "#1E1E1C", marginTop: "auto" }}>{fmt(calls[k])} on the call list</span>
            <SheetButton path={`/api/versions/${versionId}/sheets/web/${k}`} disabled={!all[k]} />
          </div>
        ))}
      </div>
      <span style={{ fontSize: 11, color: "#5E5A52" }}>
        Each sheet has a Summary tab (key numbers, by area, by segment, top sites, busiest neighbourhoods), the full Merchants list with links and filters, and a live Pivot of area × segment.
      </span>

      {byArea.length > 1 && (
        <div style={{ overflowX: "auto" }}>
          <div style={{ minWidth: 700 }}>
            <div className="m web-area" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
              <span>AREA</span><span>MERCHANTS</span>
              {WEB_KINDS.map(([k, l, c]) => <span key={k} style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><span style={{ width: 8, height: 8, background: c, flexShrink: 0 }} />{l.toUpperCase()}</span>)}
            </div>
            {byArea.map((x) => (
              <div key={x.a} className="web-area" style={{ fontSize: 12, padding: "5px 0", borderBottom: "1px solid #E2DDD1", alignItems: "center" }}>
                <span>{x.a}</span><span className="m">{fmt(x.n)}</span>
                {WEB_KINDS.map(([k]) => {
                  const s = share(k, x.c, x.n), base = share(k);
                  return (
                    <span key={k} title={`${fmt(x.c[k])} merchants`} style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
                      <span className="m" style={{ color: s - base >= 5 ? "#A8371F" : undefined, fontWeight: s - base >= 5 ? 600 : 400 }}>{pct(s, 0)}</span>
                      <span className="m" style={{ fontSize: 10, color: "#8A8478" }}>{fmt(x.c[k])}</span>
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
          <span style={{ fontSize: 11, color: "#5E5A52" }}>Red = at least 5 points above the all-area share.</span>
        </div>
      )}
    </div>
  );
}
