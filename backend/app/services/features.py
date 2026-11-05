"""Feature list: every field Google returns for a merchant, how complete it is, and what is in it.

A feature is a field of the stored Places payload. Nested fields are broken down by path:
  paymentOptions.acceptsCreditCards   a field inside an object
  reviews[].rating                    a field inside each item of a list
A merchant fills a field when it has a value there that isn't empty ("", [], {} or null). False counts as filled:
it is an answer. Completeness = merchants that fill it / merchants in the version."""

import re
import statistics
from collections import Counter

MAX_DISTINCT = 5000  # distinct values tracked per field; more and the count shows as "5,000+"
LONG_TEXT = 80  # longer strings are free text: lengths are profiled, not the values
TOP = 8  # top values kept per field


def _kind(v) -> str:
    if isinstance(v, bool):
        return "yes/no"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "text"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "object"
    return "empty"


def _filled(v) -> bool:
    return v is not None and v != "" and v != [] and v != {}


class _Stat:
    __slots__ = ("kinds", "places", "values", "nums", "lens", "text_lens", "capped", "example")

    def __init__(self):
        self.kinds: Counter = Counter()
        self.places = 0
        self.values: Counter = Counter()
        self.nums: list[float] = []
        self.lens: list[int] = []  # items per list
        self.text_lens: list[int] = []
        self.capped = False
        self.example = None

    def add(self, v):
        if isinstance(v, bool) or isinstance(v, (int, float)) or isinstance(v, str):
            if isinstance(v, str) and len(v) > LONG_TEXT:
                self.text_lens.append(len(v))
            else:
                if isinstance(v, str):
                    self.text_lens.append(len(v))
                elif not isinstance(v, bool):
                    self.nums.append(float(v))
                if v in self.values or len(self.values) < MAX_DISTINCT:
                    self.values[v] += 1
                else:
                    self.capped = True
            if self.example is None:
                self.example = v


class Profiler:
    """Feed it payloads one at a time (so a whole version never sits in memory), then read rows()."""

    def __init__(self):
        self.n = 0
        self.stats: dict[str, _Stat] = {}
        self.parent: dict[str, str | None] = {}

    def _s(self, path: str, parent: str | None) -> _Stat:
        s = self.stats.get(path)
        if s is None:
            s = self.stats[path] = _Stat()
            self.parent[path] = parent
        return s

    def add(self, data: dict):
        self.n += 1
        seen: set[str] = set()
        self._walk(data or {}, "", None, seen)
        for p in seen:
            self.stats[p].places += 1

    def _walk(self, obj: dict, prefix: str, parent: str | None, seen: set):
        for k, v in obj.items():
            path = f"{prefix}{k}"
            s = self._s(path, parent)
            s.kinds[_kind(v)] += 1
            if not _filled(v):
                continue
            seen.add(path)
            if isinstance(v, dict):
                self._walk(v, path + ".", path, seen)
            elif isinstance(v, list):
                s.lens.append(len(v))
                for item in v:
                    if isinstance(item, dict):
                        self._walk(item, path + "[].", path, seen)
                    elif _filled(item) and not isinstance(item, list):
                        s.add(item)  # a list of plain values: its values are profiled on the list itself
            else:
                s.add(v)

    def rows(self) -> list[dict]:
        out = []
        for path, s in self.stats.items():
            par = self.parent[path]
            kind = next((k for k, _ in s.kinds.most_common() if k != "empty"), "empty")
            pn = self.stats[par].places if par else self.n
            r = {"path": path, "parent": par, "key": re.split(r"\[\]\.|\.", path)[-1], "depth": path.count("."),
                 "label": label(path), "kind": kind, "places": s.places, "pct": 100 * s.places / max(1, self.n),
                 "pct_parent": 100 * s.places / max(1, pn), "children": 0, "nested": 0,
                 "distinct": len(s.values), "distinct_capped": s.capped,
                 "top": [[_short(v), c] for v, c in s.values.most_common(TOP)] if s.values else [],
                 "values": sum(s.values.values()), "example": _short(s.example)}
            if s.nums:
                r["num"] = {"min": min(s.nums), "median": statistics.median(s.nums), "max": max(s.nums)}
            if s.lens:
                r["items"] = {"mean": sum(s.lens) / len(s.lens), "max": max(s.lens)}
            if s.text_lens:
                r["text"] = {"mean": sum(s.text_lens) / len(s.text_lens), "max": max(s.text_lens)}
            r["unique"] = bool(s.values) and r["distinct"] >= 0.95 * max(1, r["values"]) and r["values"] > 20
            r["free_text"] = not s.values and bool(s.text_lens)
            out.append(r)
        by = {r["path"]: r for r in out}
        for r in out:  # direct children, and every field below
            p = r["parent"]
            if p:
                by[p]["children"] += 1
            while p:
                by[p]["nested"] += 1
                p = by[p]["parent"]
        return sorted(out, key=lambda r: (-r["pct"], r["path"]))


def _short(v):
    if isinstance(v, str) and len(v) > LONG_TEXT:
        return v[:LONG_TEXT] + "…"
    return v


def label(path: str) -> str:
    """paymentOptions.acceptsCreditCards → Accepts credit cards; reviews[].rating → Rating."""
    key = re.split(r"\[\]\.|\.", path)[-1]
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", key).replace("_", " ").split()
    s = " ".join(w if w.isupper() and len(w) > 1 else w.lower() for w in words)
    s = " ".join(ACRONYM.get(w.lower(), w) for w in s.split())
    return s[:1].upper() + s[1:]


ACRONYM = {"uri": "URI", "utc": "UTC", "nfc": "NFC", "id": "ID", "ev": "EV", "url": "URL", "adr": "ADR"}


BANDS = [("complete", "Complete", 90), ("mostly", "Mostly filled", 50), ("partial", "Partial", 10), ("rare", "Rare", 0)]


def band(pct: float) -> str:
    return next(k for k, _, lo in BANDS if pct >= lo)


def summary(rows: list[dict], n: int) -> dict:
    top = [r for r in rows if r["depth"] == 0 and not r["parent"]]
    nested = [r for r in rows if r["parent"]]
    count = lambda rs: {k: sum(band(r["pct"]) == k for r in rs) for k, _, _ in BANDS}  # noqa: E731
    return {"merchants": n, "features": len(top), "nested": len(nested), "with_nested": sum(r["children"] > 0 for r in top),
            "usable": sum(r["pct"] >= 50 for r in top), "bands": count(top), "bands_nested": count(nested),
            "band_names": [{"k": k, "l": lab, "min": lo} for k, lab, lo in BANDS], "rows": rows}
