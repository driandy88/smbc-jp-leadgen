"""Administrative boundaries (MLIT N03, ward level) and H3 coverage for the Scout region picker.

N03 is Japan's official boundary set and splits designated cities into wards (区), which GADM
does not. The simplified GeoJSON in data/boundaries is built from the 2024-01-01 release for
Osaka (27) and Kyoto (26) prefectures. GADM via config/parameters.py stays as the fallback for
cities not covered here.
"""

import json
import math
from functools import lru_cache

import h3
from shapely import STRtree, points
from shapely.geometry import Point, mapping, shape
from shapely.prepared import prep

from app.settings import REPO_ROOT

BOUNDARY_FILE = REPO_ROOT / "data" / "boundaries" / "n03_kansai.geojson"

# Average hexagon area in km² per resolution (H3 docs)
H3_AREA_KM2 = {6: 36.13, 7: 5.161, 8: 0.7373, 9: 0.1053, 10: 0.01504, 11: 0.002149}

CITY_EN = {"大阪市": "Osaka", "京都市": "Kyoto", "堺市": "Sakai"}
WARD_EN = {
    "北区": "Kita", "都島区": "Miyakojima", "福島区": "Fukushima", "此花区": "Konohana", "西区": "Nishi",
    "港区": "Minato", "大正区": "Taisho", "天王寺区": "Tennoji", "浪速区": "Naniwa", "西淀川区": "Nishiyodogawa",
    "東淀川区": "Higashiyodogawa", "東成区": "Higashinari", "生野区": "Ikuno", "旭区": "Asahi", "城東区": "Joto",
    "阿倍野区": "Abeno", "住吉区": "Sumiyoshi", "東住吉区": "Higashisumiyoshi", "西成区": "Nishinari",
    "淀川区": "Yodogawa", "鶴見区": "Tsurumi", "住之江区": "Suminoe", "平野区": "Hirano", "中央区": "Chuo",
    "上京区": "Kamigyo", "左京区": "Sakyo", "中京区": "Nakagyo", "東山区": "Higashiyama", "下京区": "Shimogyo",
    "南区": "Minami", "右京区": "Ukyo", "伏見区": "Fushimi", "山科区": "Yamashina", "西京区": "Nishikyo",
    "堺区": "Sakai", "中区": "Naka", "東区": "Higashi", "美原区": "Mihara",
}
# Shown first in the picker
FEATURED = ["osaka-shi", "kyoto-shi", "sakai-shi"]


def _slug(muni: str, code: str) -> str:
    en = CITY_EN.get(muni)
    return f"{en.lower()}-shi" if en else f"m{code}"


@lru_cache
def _load() -> dict:
    gj = json.loads(BOUNDARY_FILE.read_text(encoding="utf-8"))
    cities: dict[str, dict] = {}
    areas: dict[str, dict] = {}
    for f in gj["features"]:
        p = f["properties"]
        muni, ward, code = p["muni"] or p["pref"], p["ward"] or "", p["code"]
        # Designated cities group their wards; other municipalities are a single-area city
        city_key = _slug(muni, code)
        geom = shape(f["geometry"])
        c = cities.setdefault(city_key, {"key": city_key, "jp": muni, "en": CITY_EN.get(muni, ""),
                                         "pref": p["pref"], "areas": []})
        a = {"code": code, "city": city_key, "jp": ward or muni,
             "en": WARD_EN.get(ward, "") if ward else CITY_EN.get(muni, ""), "geom": geom}
        c["areas"].append(code)
        areas[code] = a
    return {"cities": cities, "areas": areas}


def cities() -> list[dict]:
    data = _load()
    out = []
    for key, c in data["cities"].items():
        geoms = [data["areas"][code]["geom"] for code in c["areas"]]
        km2 = sum(_km2(g) for g in geoms)
        out.append({"key": key, "jp": c["jp"], "en": c["en"], "pref": c["pref"],
                    "areas": len(c["areas"]), "km2": round(km2, 1)})
    out.sort(key=lambda c: (FEATURED.index(c["key"]) if c["key"] in FEATURED else 99, c["pref"], c["jp"]))
    return out


def city_areas(city_key: str, res: int) -> list[dict]:
    data = _load()
    c = data["cities"].get(city_key)
    if not c:
        raise KeyError(city_key)
    out = []
    for code in c["areas"]:
        a = data["areas"][code]
        out.append({"code": code, "jp": a["jp"], "en": a["en"], "km2": round(_km2(a["geom"]), 2),
                    "cells": len(area_hexes(code, res))})
    out.sort(key=lambda a: a["code"])
    return out


def area(code: str) -> dict:
    return _load()["areas"][code]


def area_geojson(codes: list[str]) -> dict:
    data = _load()
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"code": c, "jp": data["areas"][c]["jp"], "en": data["areas"][c]["en"]},
         "geometry": mapping(data["areas"][c]["geom"])}
        for c in codes if c in data["areas"]]}


@lru_cache(maxsize=512)
def area_hexes(code: str, res: int) -> frozenset[str]:
    """Cells whose centre lies inside the area (no buffer, unlike the city-wide pipeline)."""
    geom = area(code)["geom"]
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    hexes: set[str] = set()
    for poly in polys:
        hexes.update(h3.polyfill(mapping(poly), res, geo_json_conformant=True))
    if not hexes:
        # Tiny areas: take the cell containing the centroid
        pt = geom.representative_point()
        hexes.add(h3.geo_to_h3(pt.y, pt.x, res))
    return frozenset(hexes)


def selection_hexes(codes: list[str], res: int) -> dict[str, str]:
    """hex -> area code. A cell on a shared border goes to the first area that claims it."""
    out: dict[str, str] = {}
    for code in codes:
        for hx in sorted(area_hexes(code, res)):
            out.setdefault(hx, code)
    return out


class AreaLocator:
    """Point-in-polygon lookup for assigning places to the selected areas."""

    def __init__(self, codes: list[str]):
        self._areas = [(c, prep(area(c)["geom"])) for c in codes]

    def locate(self, lat: float | None, lng: float | None) -> str | None:
        if lat is None or lng is None:
            return None
        pt = Point(lng, lat)
        for code, geom in self._areas:
            if geom.contains(pt):
                return code
        return None


@lru_cache
def _tree() -> tuple[list[str], STRtree]:
    data = _load()
    codes = list(data["areas"])
    return codes, STRtree([data["areas"][c]["geom"] for c in codes])


def locate_many(lat, lng) -> list[str]:
    """The ward / municipality each point lies in, from every boundary we hold; 'outside' if none."""
    codes, tree = _tree()
    out = ["outside"] * len(lat)
    pts = points([[x if x == x else 0.0, y if y == y else 0.0] for x, y in zip(lng, lat)])
    for i, j in zip(*tree.query(pts, predicate="within")):
        out[i] = codes[j]
    return out


def area_name(code: str) -> str:
    a = _load()["areas"].get(code)
    return (a["en"] or a["jp"]) if a else "Outside"


def _km2(geom) -> float:
    # Equal-area enough at Kansai latitudes: degrees -> km with cos(lat) correction
    lat = geom.centroid.y
    return geom.area * (111.32 ** 2) * math.cos(math.radians(lat))
