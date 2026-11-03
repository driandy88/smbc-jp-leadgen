"""Named nightlife / dining districts and the business segment of a merchant.

Sales teams talk about "Umeda" or "Namba", not wards or hexes, so each merchant is tagged with the
nearest named district within reach. Merchants away from every listed district fall back to their
ward ("Kita · other").
"""

import math

import numpy as np

# (English, Japanese, lat, lng) for station areas and well-known dining districts
DISTRICTS = [
    # Osaka · Kita
    ("Umeda", "梅田", 34.7025, 135.4983), ("Kitashinchi", "北新地", 34.6977, 135.4973),
    ("Chayamachi", "茶屋町", 34.7075, 135.4995), ("Nakazakicho", "中崎町", 34.7068, 135.5048),
    ("Tenma", "天満", 34.7046, 135.5117), ("Tenjinbashi-suji", "天神橋筋", 34.7110, 135.5112),
    ("Ogimachi", "扇町", 34.7020, 135.5105), ("Temmabashi", "天満橋", 34.6928, 135.5143),
    ("Fukushima", "福島", 34.6966, 135.4867), ("Noda", "野田", 34.6935, 135.4740),
    ("Juso", "十三", 34.7205, 135.4830), ("Shin-Osaka", "新大阪", 34.7334, 135.5002),
    ("Nakanoshima", "中之島", 34.6930, 135.4930), ("Sakuranomiya", "桜ノ宮", 34.7055, 135.5240),
    # Osaka · Chuo / Minami
    ("Yodoyabashi", "淀屋橋", 34.6925, 135.5013), ("Kitahama", "北浜", 34.6917, 135.5065),
    ("Honmachi", "本町", 34.6823, 135.4985), ("Sakaisuji-Honmachi", "堺筋本町", 34.6825, 135.5065),
    ("Shinsaibashi", "心斎橋", 34.6745, 135.5005), ("Amerikamura", "アメリカ村", 34.6722, 135.4980),
    ("Dotonbori", "道頓堀", 34.6687, 135.5013), ("Namba", "難波", 34.6655, 135.5010),
    ("Sennichimae", "千日前", 34.6655, 135.5050), ("Nipponbashi", "日本橋", 34.6615, 135.5065),
    ("Tanimachi", "谷町", 34.6800, 135.5165), ("Uehonmachi", "上本町", 34.6650, 135.5205),
    ("Morinomiya", "森ノ宮", 34.6810, 135.5340), ("Osaka Castle", "大阪城", 34.6873, 135.5262),
    # Osaka · other wards
    ("Horie", "堀江", 34.6728, 135.4930), ("Kyomachibori", "京町堀", 34.6870, 135.4905),
    ("Kujo", "九条", 34.6760, 135.4745), ("Bentencho", "弁天町", 34.6693, 135.4615),
    ("Shinsekai", "新世界", 34.6525, 135.5063), ("Tennoji", "天王寺", 34.6466, 135.5133),
    ("Abeno", "阿倍野", 34.6455, 135.5140), ("Tsuruhashi", "鶴橋", 34.6656, 135.5310),
    ("Kyobashi", "京橋", 34.6967, 135.5339), ("Taisho", "大正", 34.6650, 135.4790),
    ("Nishinari", "西成", 34.6400, 135.5000), ("Showacho", "昭和町", 34.6330, 135.5170),
    ("Miyakojima", "都島", 34.7110, 135.5230), ("Esaka", "江坂", 34.7590, 135.4970),
    ("Kamishinjo", "上新庄", 34.7470, 135.5380), ("Imazato", "今里", 34.6655, 135.5420),
    ("Sumiyoshi", "住吉", 34.6110, 135.4930), ("Hirano", "平野", 34.6210, 135.5450),
    # Kyoto
    ("Kawaramachi", "河原町", 35.0037, 135.7681), ("Gion", "祇園", 35.0037, 135.7756),
    ("Pontocho", "先斗町", 35.0050, 135.7710), ("Kiyamachi", "木屋町", 35.0070, 135.7705),
    ("Shijo-Karasuma", "四条烏丸", 35.0036, 135.7595), ("Nishiki", "錦市場", 35.0050, 135.7650),
    ("Kyoto Station", "京都駅", 34.9858, 135.7588), ("Sanjo", "三条", 35.0090, 135.7720),
    ("Demachiyanagi", "出町柳", 35.0300, 135.7730), ("Kitaoji", "北大路", 35.0440, 135.7590),
    ("Nijo", "二条", 35.0110, 135.7420), ("Fushimi", "伏見", 34.9340, 135.7650),
    # Sakai
    ("Sakai-Higashi", "堺東", 34.5733, 135.4830), ("Sakai Station", "堺駅", 34.5810, 135.4660),
    ("Nakamozu", "中百舌鳥", 34.5560, 135.5030), ("Mikunigaoka", "三国ヶ丘", 34.5670, 135.4890),
]
REACH_M = 700  # a merchant belongs to a district when it is this close to its centre


def _xy(lat, lng, lat0: float):
    """Metres on a local flat projection; fine at city scale."""
    return np.asarray(lng) * 111_320 * math.cos(math.radians(lat0)), np.asarray(lat) * 110_540


def assign(lat, lng, ward_en) -> tuple[list[str], list[str]]:
    """Nearest named district within REACH_M, else '<ward> · other'. Returns (English, Japanese)."""
    lat, lng = np.asarray(lat, dtype=float), np.asarray(lng, dtype=float)
    if not len(lat):
        return [], []
    lat0 = float(np.nanmean(lat)) if np.isfinite(lat).any() else 35.0
    px, py = _xy(lat, lng, lat0)
    dx, dy = _xy([d[2] for d in DISTRICTS], [d[3] for d in DISTRICTS], lat0)
    d2 = (px[:, None] - dx[None, :]) ** 2 + (py[:, None] - dy[None, :]) ** 2
    near = np.nanargmin(np.where(np.isnan(d2), np.inf, d2), axis=1)
    ok = np.sqrt(d2[np.arange(len(lat)), near]) <= REACH_M
    en = [DISTRICTS[i][0] if o else f"{w} · other" for i, o, w in zip(near, ok, ward_en)]
    jp = [DISTRICTS[i][1] if o else "" for i, o in zip(near, ok)]
    return en, jp


def hotspots(lat, lng, radius_m: float = 300, spacing_m: float = 700, top: int = 8) -> list[dict]:
    """Densest spots without a grid: count merchants within radius_m of each merchant (a moving
    circle), take the highest as a hotspot, skip anything within spacing_m of one already taken."""
    lat, lng = np.asarray(lat, dtype=float), np.asarray(lng, dtype=float)
    m = np.isfinite(lat) & np.isfinite(lng)
    idx = np.flatnonzero(m)
    if len(idx) < 5:
        return []
    lat0 = float(lat[m].mean())
    x, y = _xy(lat[m], lng[m], lat0)
    counts = np.zeros(len(idx), dtype=int)
    for s in range(0, len(idx), 2000):  # chunked so memory stays small for large runs
        d2 = (x[s:s + 2000, None] - x[None, :]) ** 2 + (y[s:s + 2000, None] - y[None, :]) ** 2
        counts[s:s + 2000] = (d2 <= radius_m ** 2).sum(axis=1)
    area_km2 = math.pi * (radius_m / 1000) ** 2
    floor = max(5, np.percentile(counts, 75))
    out: list[dict] = []
    for i in np.argsort(-counts):
        if counts[i] < floor or len(out) >= top:
            break
        if any((x[i] - h["_x"]) ** 2 + (y[i] - h["_y"]) ** 2 < spacing_m ** 2 for h in out):
            continue
        out.append({"_x": x[i], "_y": y[i], "row": int(idx[i]), "lat": float(lat[idx[i]]), "lng": float(lng[idx[i]]),
                    "core": int(counts[i]), "density_km2": round(counts[i] / area_km2)})
    return out


# Business segments for F&B merchants, matched on words in Google's primaryType code (first match wins)
SEGMENTS = [
    # Before bars and cafes: 'barbecue' contains 'bar', 'steak' contains 'tea'
    ("Yakiniku & grill", ("yakiniku", "barbecue", "steak", "grill", "teppanyaki", "korean_barbecue")),
    ("Izakaya & bars", ("izakaya", "bar", "pub", "wine", "beer", "sake", "night_club", "yakitori", "lounge")),
    ("Cafe, bakery & sweets", ("cafe", "coffee", "bakery", "dessert", "confection", "tea", "ice_cream", "cake",
                               "donut", "juice", "chocolate", "candy", "patisserie", "sweets", "pastry", "creperie")),
    ("Noodles", ("ramen", "udon", "soba", "noodle")),
    ("Japanese dining", ("sushi", "japanese", "tonkatsu", "tempura", "unagi", "kaiseki", "shabu", "sukiyaki",
                         "okonomiyaki", "takoyaki", "oden", "gyudon", "monja", "kushikatsu", "seafood", "fugu")),
    ("World cuisine", ("chinese", "italian", "french", "korean", "indian", "thai", "vietnamese", "spanish",
                       "mexican", "american", "pizza", "mediterranean", "turkish", "greek", "asian", "european",
                       "western", "brazilian", "nepalese", "indonesian", "taiwanese", "hawaiian", "middle_eastern",
                       "bistro", "brasserie", "dumpling")),
    ("Fast food & takeaway", ("fast_food", "hamburger", "takeaway", "delivery", "sandwich", "food_court", "meal",
                              "bento", "fried_chicken", "curry", "hot_dog", "bagel", "snack")),
    ("Restaurants (general)", ("restaurant", "diner", "buffet", "dining", "family", "cafeteria", "canteen", "food")),
]


def segment(primary_type: str | None, fnb: str) -> str:
    if fnb == "no":
        return "Not F&B"
    if fnb == "related":
        return "F&B-related (karaoke, liquor, venues)"
    t = primary_type or ""
    for name, words in SEGMENTS:
        if any(w in t for w in words):
            return name
    return "Other F&B"
