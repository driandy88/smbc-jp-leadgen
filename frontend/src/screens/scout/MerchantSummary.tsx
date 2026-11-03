import { Fragment, useState } from "react";
import { fmt, pct } from "../../lib/format";
import { Profile } from "./types";

export const FNB = [
  { k: "core", l: "F&B", c: "#1E1E1C" },
  { k: "related", l: "F&B-related", c: "#C8442B" },
  { k: "no", l: "Not F&B", c: "#C9C2B2" },
] as const;

const Card = ({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) => (
  <div className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span className="lbl">{title}</span>
      {meta && <span className="m" style={{ fontSize: 11, color: "#5E5A52", textAlign: "right" }}>{meta}</span>}
    </div>
    {children}
  </div>
);

const Strip = ({ items }: { items: { v: string; l: string; s?: string; accent?: boolean }[] }) => (
  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(150px, 100%), 1fr))", borderTop: "1px solid #1E1E1C", borderBottom: "1px solid #D8D3C7" }}>
    {items.map((s, i) => (
      <div key={s.l} style={{ padding: "12px 12px 12px 0", paddingLeft: i ? 12 : 0, borderLeft: i ? "1px solid #E2DDD1" : undefined, display: "flex", flexDirection: "column", gap: 3 }}>
        <span className="m" style={{ fontSize: 24, letterSpacing: "-0.02em", color: s.accent ? "#C8442B" : undefined }}>{s.v}</span>
        <span style={{ fontSize: 12 }}>{s.l}</span>
        {s.s && <span style={{ fontSize: 11, color: "#5E5A52", lineHeight: 1.45 }}>{s.s}</span>}
      </div>
    ))}
  </div>
);

/** Stacked F&B / related / not bar for one row. */
const FnbBar = ({ core, related, no, h = 10 }: { core: number; related: number; no: number; h?: number }) => {
  const n = Math.max(1, core + related + no);
  const v = { core, related, no };
  return (
    <div style={{ display: "flex", height: h, gap: 1, background: "#EEEAE0" }} title={`F&B ${core} · related ${related} · not ${no}`}>
      {FNB.map((x) => <span key={x.k} style={{ width: `${(100 * v[x.k]) / n}%`, background: x.c, minWidth: v[x.k] ? 2 : 0 }} />)}
    </div>
  );
};

const FnbKey = () => (
  <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px", fontSize: 11, color: "#5E5A52" }}>
    {FNB.map((x) => <span key={x.k} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><span style={{ width: 9, height: 9, background: x.c }} />{x.l}</span>)}
  </div>
);

/** Rule-based findings from the merchant mix, hexes and contact data. */
export function Insights({ p }: { p: Profile }) {
  const items: { k: string; t: string }[] = p.insights || [];
  if (!items.length) return null;
  return (
    <Card title="What stands out" meta="computed from this list">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(340px, 100%), 1fr))", gap: "0 28px" }}>
        {items.map((i) => (
          <div key={i.k} style={{ display: "grid", gridTemplateColumns: "64px 1fr", gap: 12, padding: "11px 0", borderTop: "1px solid #E2DDD1", fontSize: 13, lineHeight: 1.55 }}>
            <span className="m" style={{ fontSize: 10, color: "#C8442B", paddingTop: 3, letterSpacing: "0.05em" }}>{i.k.toUpperCase()}</span>
            <span>{i.t}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

/** Unique merchants by area: how many, which types, and whether they are F&B. */
export function MerchantMix({ p }: { p: Profile }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!p.type_mix || !p.areas?.[0]?.fnb) return null;
  const f = p.fnb;
  const areas: any[] = p.areas;
  const max = Math.max(1, ...areas.map((a) => a.places));
  const maxType = Math.max(1, ...p.type_mix.map((t: any) => t.n));

  return (
    <Card title="Unique merchants · by area, type and F&B" meta="click an area for its full type list">
      <Strip items={[
        { v: fmt(p.rows), l: "unique merchants", s: `${fmt(areas.length)} areas · ${fmt(p.overview.types)} types` },
        ...FNB.map((x) => ({ v: fmt(f[x.k].n), l: x.l, s: pct(f[x.k].pct), accent: x.k === "core" })),
      ]} />

      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: 940 }}>
          <div className="m mix-grid" style={{ fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>AREA</span><span>MERCHANTS</span><span>F&B</span><span>RELATED</span><span>NOT F&B</span><span>F&B MIX</span><span>TOP TYPES</span><span title="phone or website">CONTACTABLE</span><span title="branches of brands with 3+ outlets">CHAINS</span>
          </div>
          {areas.map((a) => {
            const isOpen = open === a.code;
            return (
              <Fragment key={a.code}>
                <button className="mix-grid mix-row" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : a.code)}>
                  <span style={{ display: "flex", flexDirection: "column", textAlign: "left" }}>
                    <span style={{ fontSize: 13 }}>{isOpen ? "▾" : "▸"} {a.en}</span>
                    <span className="jp" style={{ fontSize: 10, color: "#8A8478", paddingLeft: 12 }}>{a.jp}</span>
                  </span>
                  <span style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    <span className="m">{fmt(a.places)}</span>
                    <span style={{ height: 3, background: "#1E1E1C", width: `${(100 * a.places) / max}%` }} />
                  </span>
                  <span className="m">{fmt(a.fnb.core)}</span>
                  <span className="m" style={{ color: a.fnb.related ? "#A8371F" : "#8A8478" }}>{fmt(a.fnb.related)}</span>
                  <span className="m" style={{ color: "#5E5A52" }}>{fmt(a.fnb.no)}</span>
                  <span style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    <FnbBar {...a.fnb} />
                    <span className="m" style={{ fontSize: 10, color: "#5E5A52" }}>{pct((100 * a.fnb.core) / Math.max(1, a.places), 0)} F&B</span>
                  </span>
                  <span style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {a.types.filter((t: any) => !t.other).slice(0, 3).map((t: any) => <span key={t.t} className="jp type-chip">{t.t} <span className="m">{t.n}</span></span>)}
                  </span>
                  <span className="m">{pct((100 * a.contact.either) / Math.max(1, a.places), 0)}</span>
                  <span className="m" style={{ color: "#5E5A52" }}>{fmt(a.chains)}</span>
                </button>
                {isOpen && (
                  <div style={{ padding: "10px 0 14px 12px", borderBottom: "1px solid #E2DDD1", background: "#F3F0E8", display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="m" style={{ fontSize: 10, color: "#5E5A52" }}>{fmt(a.type_count)} TYPES IN {a.en.toUpperCase()} · phone {fmt(a.contact.phone)} · website {fmt(a.contact.web)} · neither {fmt(a.contact.neither)}</span>
                    <TypeRows rows={a.types} max={Math.max(1, ...a.types.map((t: any) => t.n))} />
                  </div>
                )}
              </Fragment>
            );
          })}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <span className="lbl" style={{ color: "#5E5A52" }}>Merchant types · all areas · F&B or not</span>
          <FnbKey />
        </div>
        <TypeRows rows={p.type_mix} max={maxType} />
      </div>
    </Card>
  );
}

function TypeRows({ rows, max }: { rows: any[]; max: number }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(420px, 100%), 1fr))", gap: "0 28px" }}>
      {rows.map((t) => {
        const verdict = t.core === t.n ? "F&B" : t.no === t.n ? "Not F&B" : t.related === t.n ? "Related" : "Mixed";
        return (
          <div key={t.t} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(80px, 1.2fr) 44px 64px", gap: 10, alignItems: "center", fontSize: 12, padding: "5px 0", borderBottom: "1px solid #E2DDD1" }}>
            <span className="jp" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: t.other ? "#5E5A52" : undefined }} title={t.t}>{t.t}</span>
            <div style={{ width: `${Math.max(4, (100 * t.n) / max)}%` }}><FnbBar core={t.core} related={t.related} no={t.no} /></div>
            <span className="m" style={{ textAlign: "right" }}>{fmt(t.n)}</span>
            <span className="m" style={{ fontSize: 10, textAlign: "right", color: verdict === "F&B" ? "#1E1E1C" : verdict === "Not F&B" ? "#8A8478" : "#A8371F" }}>{verdict}</span>
          </div>
        );
      })}
    </div>
  );
}

const SPLIT = [
  { k: "both", l: "Phone + website", c: "#1E1E1C" },
  { k: "phone_only", l: "Phone only", c: "#6E685C" },
  { k: "web_only", l: "Website only", c: "#A39B88" },
  { k: "neither", l: "Neither · walk-in only", c: "#C8442B" },
] as const;
const KIND_C: Record<string, string> = { own: "#1E1E1C", social: "#3E5A63", portal: "#D48E78" };

/** How each merchant can be reached. Google has phone and website, no email. */
export function Contactability({ p }: { p: Profile }) {
  const c = p.contact;
  if (!c) return null;
  const areas = [...p.areas].filter((a: any) => a.contact && a.code !== "outside").sort((x: any, y: any) => x.contact.either / x.places - y.contact.either / y.places);
  const label = { core: "F&B", related: "F&B-related", no: "Not F&B" } as Record<string, string>;

  return (
    <Card title="Contactability · can we reach them?" meta="phone and website from Google Places">
      <Strip items={[
        { v: pct(c.either_pct, 0), l: "reachable by phone or website", s: `${fmt(c.either)} of ${fmt(c.n)} merchants`, accent: true },
        { v: fmt(c.phone), l: "have a phone number", s: pct(c.phone_pct) },
        { v: fmt(c.web), l: "have a website", s: `${pct(c.web_pct)} · ${fmt(c.own_site)} their own site` },
        { v: fmt(c.neither), l: "no phone, no website", s: `${pct(c.neither_pct)} · walk-in only` },
        { v: fmt(c.cash_callable.n), l: "cash / no-card merchants with a phone", s: `of ${fmt(c.cash_callable.of)} operational · the call list` },
      ]} />

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", height: 18, gap: 2 }}>
          {SPLIT.map((x) => <span key={x.k} title={`${x.l} · ${c.split[x.k].n}`} style={{ width: `${c.split[x.k].pct}%`, background: x.c, minWidth: c.split[x.k].n ? 3 : 0 }} />)}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 18px", fontSize: 12 }}>
          {SPLIT.map((x) => (
            <span key={x.k} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <span style={{ width: 9, height: 9, background: x.c }} />{x.l} <span className="m">{fmt(c.split[x.k].n)}</span><span className="m" style={{ color: "#8A8478", fontSize: 11 }}>{pct(c.split[x.k].pct, 0)}</span>
            </span>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(360px, 100%), 1fr))", gap: 28 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <span className="lbl" style={{ color: "#5E5A52" }}>What the website link is</span>
          {c.web_kinds.map((k: any) => (
            <div key={k.k} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 54px 44px", gap: 8, fontSize: 12, alignItems: "baseline" }}>
                <span>{k.label}</span><span className="m" style={{ textAlign: "right" }}>{fmt(k.n)}</span><span className="m" style={{ textAlign: "right", color: "#5E5A52" }}>{pct(k.pct, 0)}</span>
              </div>
              <div style={{ height: 6, background: "#E2DDD1" }}><div style={{ height: 6, width: `${k.pct}%`, background: KIND_C[k.k] }} /></div>
              {k.hosts.length > 0 && <span className="m" style={{ fontSize: 10.5, color: "#5E5A52" }}>{k.hosts.map((h: any) => `${h.host} ${h.n}`).join(" · ")}</span>}
            </div>
          ))}
          <div style={{ border: "1px dashed #A39B88", padding: "10px 12px", fontSize: 12, lineHeight: 1.5, color: "#3A3833" }}>
            <span className="m" style={{ fontSize: 10, color: "#C8442B" }}>EMAIL · NOT AVAILABLE </span>
            Google Places has no email field. The {fmt(c.own_site)} merchants with their own website are where a contact address can usually be found.
          </div>
          {c.by_fnb?.length > 1 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="lbl" style={{ color: "#5E5A52" }}>Reachable by F&B class</span>
              {c.by_fnb.map((r: any) => (
                <div key={r.fnb} style={{ display: "grid", gridTemplateColumns: "92px 1fr 44px", gap: 8, alignItems: "center", fontSize: 12 }}>
                  <span>{label[r.fnb]} <span className="m" style={{ color: "#8A8478", fontSize: 10 }}>{fmt(r.n)}</span></span>
                  <div style={{ height: 6, background: "#E2DDD1" }}><div style={{ height: 6, width: `${r.either_pct}%`, background: FNB.find((x) => x.k === r.fnb)!.c }} /></div>
                  <span className="m" style={{ textAlign: "right" }}>{pct(r.either_pct, 0)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="lbl" style={{ color: "#5E5A52", paddingBottom: 4 }}>By area · least reachable first</span>
          <div className="m" style={{ display: "grid", gridTemplateColumns: "minmax(70px, 1fr) 50px 50px 50px 60px", gap: 8, fontSize: 10, color: "#5E5A52", borderBottom: "1px solid #1E1E1C", padding: "4px 0" }}>
            <span>AREA</span><span style={{ textAlign: "right" }}>PHONE</span><span style={{ textAlign: "right" }}>WEB</span><span style={{ textAlign: "right" }}>NEITHER</span><span style={{ textAlign: "right" }}>REACHABLE</span>
          </div>
          <div style={{ maxHeight: 300, overflowY: "auto" }}>
            {areas.map((a: any) => {
              const r = (100 * a.contact.either) / Math.max(1, a.places);
              return (
                <div key={a.code} className="m" style={{ display: "grid", gridTemplateColumns: "minmax(70px, 1fr) 50px 50px 50px 60px", gap: 8, fontSize: 12, padding: "5px 0", borderBottom: "1px solid #E2DDD1" }}>
                  <span>{a.en}</span>
                  <span style={{ textAlign: "right" }}>{fmt(a.contact.phone)}</span><span style={{ textAlign: "right" }}>{fmt(a.contact.web)}</span>
                  <span style={{ textAlign: "right", color: "#A8371F" }}>{fmt(a.contact.neither)}</span>
                  <span style={{ textAlign: "right", color: r < 70 ? "#A8371F" : undefined }}>{pct(r, 0)}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Card>
  );
}
