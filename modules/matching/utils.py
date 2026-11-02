from __future__ import annotations

import ast
import json
import re
from typing import Any

import geopandas as gpd
import google.auth
import httpx
import numpy as np
import pandas as pd
import requests as r
from google.auth.transport import requests
from loguru import logger
from rapidfuzz import fuzz, process
from sentence_transformers import SentenceTransformer

from config.bq import PROJECT

MODEL = SentenceTransformer("sentence-transformers/LaBSE")
DIM = MODEL.get_sentence_embedding_dimension()


def get_adc_access_token(scope: str = "https://www.googleapis.com/auth/cloud-platform") -> str:
    """
    Return a fresh OAuth 2.0 bearer token using the current
    Application-Default Credentials chain.

    Equivalent to `gcloud auth application-default print-access-token`
    but without spawning a subprocess.
    """
    creds, _ = google.auth.default(scopes=[scope])

    # Refresh if the cached token is missing or expired
    if not creds.valid:
        creds.refresh(requests.Request())

    return creds.token


async def get_location_text_search(textQuery: str, languageCode: str = "en-SG"):
    url = "https://places.googleapis.com/v1/places:searchText"
    token = get_adc_access_token()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": PROJECT,
        "X-Goog-FieldMask": "places.attributions,places.id,places.name",
    }

    data = {"textQuery": textQuery, "languageCode": languageCode, "maxResultCount": 1}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=data, headers=headers)
        results = response.json()
        if results.get("places"):
            return results.get("places")[0].get("id")
        else:
            return None


def get_location(address):
    token = get_adc_access_token()
    url = f"https://geocode.googleapis.com/v4beta/geocode/address/{address}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": PROJECT,
    }
    response = r.get(url, headers=headers)
    try:
        data = response.json()
    except r.JSONDecodeError:
        logger.error(f"Error parsing JSON response: {response.text}")
        return np.nan
    if data:
        try:
            return data["results"]
        except KeyError:
            logger.error(f"Unexpected response format: {data}")
            return np.nan
    else:
        return np.nan


def road_only_naive(addr):
    """Fixed version that handles different address formats"""
    addr = str(addr)
    # Combined pattern: Singapore format OR Western format
    m = re.search(
        r"\b(?:\d+[-\d]*\s+)?((?:Jln|Jalan)\s+[A-Za-z'\-\s]+?)(?:\s*,|$|\s+#)|(?:\d+[-\d]*\s+)?([A-Za-z'\-\s]+\s*(?:Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Place|Pl|Way|Crescent|Cres|Terrace|Tce))\b",
        addr,
        re.IGNORECASE,
    )
    if m:
        # Return whichever group matched (group 1 = Singapore, group 2 = Western)
        return (m.group(1) or m.group(2)).strip()


def safe_convert_customer_code(x):
    try:
        return str(int(x))
    except Exception:
        return x


def parse_cell(value: Any) -> Any:
    """
    Convert a stringified dict/list/number into its Python object.
    Returns the original value unchanged if parsing fails.

    Handles:
    - JSON         → {"a":1} , [1,2]
    - Python literal→ {'a':1} , [1,2]
    - Empty / NaN   → stays NaN/None
    """

    # keep NaN / None untouched
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return value

    # only attempt to parse strings
    if not isinstance(value, str):
        return value

    text = value.strip()

    # fast exit for plain strings that don't look like JSON / literal
    if not (text.startswith("{") or text.startswith("[") or text.startswith("(")):
        return value

    # Try JSON, then Python literal
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text)
        except Exception:
            continue

    # fallback: return as-is
    return value


def flatten_json_columns(df: pd.DataFrame, cols):
    out = df.drop(columns=cols)

    for col in cols:
        expanded_rows = df[col].apply(
            lambda x: pd.json_normalize(x) if isinstance(x, (dict, list)) else pd.DataFrame([{}])
        )
        expanded = pd.concat(expanded_rows.to_list(), ignore_index=True).add_prefix(f"{col}.").reindex(df.index)
        out = pd.concat([out, expanded], axis=1)

    return out


def load_places(raw: pd.DataFrame) -> pd.DataFrame:
    parsed = raw.applymap(parse_cell)

    json_cols = [c for c in parsed.columns if parsed[c].apply(lambda x: isinstance(x, (dict, list))).any()]

    return flatten_json_columns(parsed, json_cols)


def matching_lat_lon(aspire_data: pd.DataFrame, gmaps_data: pd.DataFrame, max_distance: 1000):
    # Convert to GeoDataFrames
    gmaps_gdf = gpd.GeoDataFrame(
        gmaps_data,
        geometry=gpd.points_from_xy(gmaps_data["location_longitude"], gmaps_data["location_latitude"]),
        crs="EPSG:4326",
    )

    aspire_gdf = gpd.GeoDataFrame(
        aspire_data,
        geometry=gpd.points_from_xy(aspire_data.salesforceLongitudeCode, aspire_data.salesforceLatitudeCode),
        crs="EPSG:4326",
    )

    # Project to meters for accurate distance calculations
    gmaps_gdf = gmaps_gdf.to_crs(epsg=3857)
    aspire_gdf = aspire_gdf.to_crs(epsg=3857)

    # Join on nearest location within 50 meters
    joined = gpd.sjoin_nearest(gmaps_gdf, aspire_gdf, how="right", distance_col="dist", max_distance=max_distance)

    return joined


def fuzzy_matching_name(df: pd.DataFrame, threshold: float = 80):
    df["fuzzy_score"] = df.apply(
        lambda row: fuzz.token_sort_ratio(
            str(row["displayName_text"]).strip().lower(), str(row["Name"]).strip().lower()
        ),
        axis=1,
    )

    df["fuzzy_rank"] = df.groupby("displayName_text")["fuzzy_score"].rank(method="first", ascending=False)
    return df


def fuzzy_matching(text_1: str, text_2: str):
    return fuzz.token_sort_ratio(text_1, text_2)


# Step 1: Clean address functions (if not done already)
def clean_address(addr):
    if pd.isna(addr):
        return ""
    addr = str(addr).lower()
    addr = re.sub(r"[^a-z0-9\s]", "", addr)  # remove punctuation
    addr = re.sub(r"\s+", " ", addr).strip()
    return addr


def address_matching(df: pd.DataFrame, df_gmaps_sg: pd.DataFrame) -> pd.DataFrame:
    # Step 2: Apply cleaning
    df["cleaned_address"] = df["customerAddress"].apply(clean_address)
    df_gmaps_sg["flattened_address"] = df_gmaps_sg["formattedAddress"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else str(x)
    )
    df_gmaps_sg["cleaned_address"] = df_gmaps_sg["flattened_address"].apply(clean_address)

    # Step 3: Fuzzy match
    def find_best_match(address, choices):
        match, score, _ = process.extractOne(address, choices, scorer=fuzz.token_set_ratio)
        return match, score

    matches = df["cleaned_address"].apply(lambda x: find_best_match(x, df_gmaps_sg["cleaned_address"]))

    df[["matched_cleaned_address", "match_score"]] = pd.DataFrame(matches.tolist(), index=df.index)

    # Step 4: Merge on the cleaned matched address
    merged_df = df.merge(
        df_gmaps_sg, left_on="matched_cleaned_address", right_on="cleaned_address", how="left", suffixes=("_sg", "_n")
    )
    return merged_df


def matching_address_manual_way(aspire: pd.DataFrame, gmaps: pd.DataFrame) -> pd.DataFrame:
    aspire_match = aspire[aspire["customerAddress"].notna()]
    aspire_match = aspire_match[aspire_match["Name"].notna()]

    res = embedding_matching(matching_lat_lon(aspire_data=aspire, gmaps_data=gmaps, max_distance=1000000))
    res["final"] = res.apply(lambda row: row["sim"] * 0.8 + row["place"] * 0.2, axis=1)
    res = res[res["final"] >= 0.6]
    return res


def embedding_matching(aspire_match: pd.DataFrame) -> pd.DataFrame:
    same_place_id = aspire_match.copy()

    uniq = pd.unique(same_place_id[["Name", "displayName_text"]].values.ravel())
    uniq_str = [str(x) if not pd.isna(x) else "" for x in uniq]
    if len(uniq_str) == 1:
        vecs = MODEL.encode([uniq_str[0]], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    else:
        vecs = MODEL.encode(uniq_str, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    vec_map = dict(zip(uniq, vecs))

    def cos(a, b):
        if a is None or b is None:
            return 0.0
        return float(np.dot(vec_map[a], vec_map[b]))

    same_place_id["sim"] = [cos(a, b) for a, b in zip(same_place_id["Name"], same_place_id["displayName_text"])]

    uniq = pd.unique(same_place_id[["customerAddress", "formattedAddress"]].values.ravel())
    uniq_str = [str(x) if not pd.isna(x) else "" for x in uniq]
    if len(uniq_str) == 1:
        vecs = MODEL.encode([uniq_str[0]], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    else:
        vecs = MODEL.encode(uniq_str, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    vec_map = dict(zip(uniq, vecs))
    same_place_id["place"] = [
        cos(a, b) for a, b in zip(same_place_id["customerAddress"], same_place_id["formattedAddress"])
    ]

    return same_place_id


def extract_street_part(addr: str) -> str:
    """
    Return a cleaned street name.
    1. Keep text only up to the first comma.
    2. Drop a leading house number like '123', '3A', '12-B'.
    3. Strip everything that is not A–Z or space.
    4. Collapse double-spaces and Title-case.
    """
    if not isinstance(addr, str):
        return ""

    # 1 ─ take the chunk before the first comma
    before_comma = addr.split(",", 1)[0]

    # 2 ─ strip a leading suite/unit like "#11-01A "
    no_unit = re.sub(r"^\s*#\S+\s+", "", before_comma)

    # 3 ─ strip a leading street number like "181 " or "3A "
    no_number = re.sub(r"^\s*\d+[A-Za-z\-]?\s+", "", no_unit)

    # 4 ─ keep letters & spaces only
    letters_only = re.sub(r"[^A-Za-z\s]", " ", no_number)

    # 5 ─ tidy whitespace and title-case
    clean = re.sub(r"\s{2,}", " ", letters_only).strip().title()
    return clean
