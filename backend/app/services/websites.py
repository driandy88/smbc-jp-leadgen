"""What a merchant's website link really is.

Google gives one website link per place, and for many merchants it is not their own site: it can be
an Instagram page, a Tabelog listing, a booking page, or the store finder of the chain or building
they belong to. Each link gets one of these kinds:

- own: the merchant's own site, including pages made on a site builder (Wix, Jimdo, gorp.jp, owst.jp…)
- group: a site shared by 3+ merchants of one run, i.e. a chain or operator (fujiofood.com, a Starbucks
  store page) or the hotel, department store or food hall the merchant sits in
- social: Instagram, Facebook, X, LINE, TikTok, link-in-bio pages
- portal: a booking page or gourmet / listing portal (TableCheck, Ikyu, Tabelog, Hot Pepper, Gurunavi,
  Retty, delivery apps…): a rented channel, not the merchant's own
"""

from urllib.parse import urlparse

import pandas as pd

KIND = {"own": "Own website", "group": "Group / chain website", "social": "Social media",
        "portal": "Booking / gourmet portal"}

SOCIAL = ("instagram.com", "facebook.com", "fb.com", "x.com", "twitter.com", "tiktok.com", "youtube.com",
          "threads.net", "threads.com", "line.me", "lin.ee", "linktr.ee", "lit.link", "ameblo.jp", "note.com",
          "pinterest.com", "xiaohongshu.com")
# Hosts where every merchant gets its own page by path, so a shared host does not mean a shared group.
# Builders that give each merchant a subdomain (gorp.jp, wixsite.com…) need no entry: each subdomain is
# its own host, used by one merchant
BUILDER = ("sites.google.com", "business.site", "goope.jp", "site.locaop.jp", "localplace.jp", "peraichi.com",
           "studio.site", "canva.site", "eonet.ne.jp", "fc2.com", "livedoor.jp", "hatenablog.com", "seesaa.net",
           "wordpress.com", "notion.site", "linkup.jp")
BOOKING = ("tablecheck.com", "yoyaku.tabelog.com", "ikyu.com", "hitosara.com", "ebica.jp", "toreta.in",
           "res-reserve.com", "airrsv.net", "omakase.in", "autoreserve.com", "resty.jp", "opentable.jp",
           "opentable.com", "pocket-concierge.jp")
AGGREGATOR = ("tabelog.com", "hotpepper.jp", "gnavi.co.jp", "retty.me", "favy.jp", "ozmall.co.jp", "tripadvisor.jp",
              "tripadvisor.com", "yelp.com", "ubereats.com", "demae-can.com", "wolt.com", "pokepara.jp",
              "navitime.co.jp", "bar-navi.suntory.co.jp", "dokonet.jp", "subsaku.com", "google.com", "google.co.jp",
              "goo.gl", "map.yahoo.co.jp", "plaza.rakuten.co.jp")
GROUP_MIN = 3  # distinct merchant names on one host


def host(url) -> str:
    if not isinstance(url, str) or not url:
        return ""
    h = urlparse(url if "//" in url else f"//{url}").netloc.lower().split(":")[0]
    return h.removeprefix("www.")


def _on(h: str, domains: tuple[str, ...]) -> bool:
    return any(h == d or h.endswith("." + d) for d in domains)


def listed_kind(url) -> str | None:
    """The kind from the host lists alone: None for no link, 'own' when the host is on no list."""
    h = host(url)
    if not h:
        return None
    if _on(h, SOCIAL):
        return "social"
    if _on(h, BUILDER):  # before the portals: sites.google.com is not google.com
        return "own"
    if _on(h, BOOKING) or _on(h, AGGREGATOR):
        return "portal"
    return "own"


def kinds(web: pd.Series, names: pd.Series) -> pd.Series:
    """Kind of every link in one run. 'group' needs the whole run: an unlisted host that 3+ differently
    named merchants link to is a chain, operator or venue site, not any one merchant's own."""
    listed = web.map(listed_kind)
    hosts = web.map(host)
    unlisted = (listed == "own") & ~hosts.map(lambda h: _on(h, BUILDER))
    shared = names[unlisted].groupby(hosts[unlisted]).nunique()
    group = unlisted & hosts.map(shared).fillna(0).ge(GROUP_MIN)
    out = listed.mask(group, "group")
    return out.astype(object).where(out.notna(), None)


def instagram(url) -> str | None:
    return url if _on(host(url), ("instagram.com",)) else None
