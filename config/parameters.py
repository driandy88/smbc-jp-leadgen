from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SHP_CITIES = {
    "Osaka": {
        "folder_type": "gadm41",
        "country_code": "JPN",
        # "2" = Osaka City (大阪市, 24 wards) · "1" = all of Osaka Prefecture (大阪府)
        "level": "2",
        # Matches NAME_2 (or NAME_1 at level 1) in gadm41_JPN_*.shp
        "city": "Osaka",
        "country_type": "non-latin",
        "local_shp_dir": str(PROJECT_ROOT / "gadm41_JPN_shp"),
        # Language of returned names/addresses ("ja" or "en")
        "language_code": "ja",
        "region_code": "JP",
    }
}

# Every keyword is searched in every hexagon, so API cost scales with the length of this list.
MAIN_KEYWORDS_QUERY = [
    "restaurant",
    "cafe",
    "bar",
    "retail store",
    "beauty salon",
]

# Extra keywords per country code, appended to MAIN_KEYWORDS_QUERY
COUNTRY_KEYWORDS_QUERY = {
    "JPN": [
        "居酒屋",
    ],
}
