from __future__ import annotations

import io
import logging

import numpy as np
import pandas as pd

from config.gcs import MATCHING_DATASET_FOLDER_NAME
from modules.google_cloud_storage.downloader import GCSDownloader
from modules.google_cloud_storage.uploader import GCSUploader
from modules.matching.address_matching import match_tables
from modules.matching.utils import (
    address_matching,
    embedding_matching,
    fuzzy_matching_name,
    get_location_text_search,
    matching_lat_lon,
    road_only_naive,
    safe_convert_customer_code,
)
from modules.matching.utils import get_location as get_location_geocoding

LOGGER = logging.getLogger("matching_pipeline")
max_distance_m = 1000
fuzzy_min_score = 80


class MatchingPipeline:
    def __init__(self):
        self.uploader = GCSUploader()
        self.downloader = GCSDownloader()

    def _geocode_missing(self, df_in: pd.DataFrame) -> None:
        """Append new (customerCode, place_id, location_type) rows into geocoding CSV for missing ones.
        Mutates the geocoding CSV on disk (idempotent via later de-duplication).
        """
        df = df_in.copy()
        df["customerAddress_custom"] = df["customerAddress"].apply(road_only_naive)

        # breakpoint()

        for _, row in df.iterrows():
            name = row.get("Name") or ""
            city = row.get("Normalized City")
            addr_custom = row.get("customerAddress_custom")
            query = f"{name}, {addr_custom}, {city}" if isinstance(addr_custom, str) else f"{name} +{city}"

            def _call(query: str):
                return get_location_geocoding(query)

            res = _call(query=query)
            rows = []
            if not res:
                continue
            if isinstance(res, list) and len(res) > 0:
                location_type = res[0].get("granularity", "APPROXIMATE")
                place_id = res[0].get("placeId")
            elif isinstance(res, str):
                location_type = "ROOFTOP"
                place_id = res
            else:
                continue
            if place_id:
                rows.append(
                    {
                        "customerCode": safe_convert_customer_code(row["customerCode"]),
                        "place_id": str(place_id),
                        "location_type": str(location_type),
                    }
                )

        if rows:
            gcs_paths = [f"{MATCHING_DATASET_FOLDER_NAME}/geocoding-matching/geocoding.csv"]
            geoc = self.downloader.download_csv_files(gcs_paths=gcs_paths)
            geoc = pd.read_csv(io.BytesIO(geoc[gcs_paths[0]])) if gcs_paths[0] in geoc else pd.DataFrame()
            new_df = pd.DataFrame(rows)
            all_df = pd.concat([geoc, new_df], ignore_index=True) if not geoc.empty else new_df
            all_df["customerCode"] = all_df["customerCode"].map(safe_convert_customer_code)
            all_df = all_df.drop_duplicates(subset=["customerCode"], keep="last")
            response = self.uploader.upload_dataframe(
                df=all_df,
                gcs_path=gcs_paths[0],
            )

            if len(response.get("successful")) > 0:
                print(f"Uploaded geocoding.csv with {len(all_df)} rows")
            else:
                print("Failed to upload geocoding.csv")

            LOGGER.info("Geocoded and appended %d rows", len(new_df))
        else:
            LOGGER.info("No new geocoding rows to append")

    async def _geocode_missing_for_non_latin(self, df_in: pd.DataFrame) -> None:
        all_df = pd.DataFrame()
        for _, row in df_in[["customerCode", "Name", "customerAddress"]].iterrows():
            customerCode = row["customerCode"]
            query = f"{row['Name']}, {row['customerAddress']}"
            place_id = await get_location_text_search(query)

            result = pd.DataFrame({"customerCode": [customerCode], "place_id": [place_id]})

            all_df = pd.concat([all_df, result], ignore_index=True).reset_index(drop=True)

        if not all_df.empty():
            gcs_paths = [f"{MATCHING_DATASET_FOLDER_NAME}/geocoding-matching/all_place_id_non_alpha.csv"]
            geoc = self.downloader.download_csv_files(gcs_paths=gcs_paths)
            geoc = pd.read_csv(io.BytesIO(geoc[gcs_paths[0]])) if gcs_paths[0] in geoc else pd.DataFrame()
            all_df = pd.concat([geoc, all_df], ignore_index=True) if not geoc.empty else all_df
            all_df["customerCode"] = all_df["customerCode"].map(safe_convert_customer_code)
            all_df = all_df.drop_duplicates(subset=["customerCode"], keep="last")
            response = self.uploader.upload_dataframe(
                df=all_df,
                gcs_path=gcs_paths[0],
            )

            if len(response.get("successful")) > 0:
                print(f"Uploaded geocoding.csv with {len(all_df) - len(geoc)} rows")
            else:
                print("Failed to upload geocoding.csv")

            LOGGER.info("Geocoded and appended %d rows", len(all_df))
        else:
            LOGGER.info("No new geocoding rows to append")

    def run_matching_for_indonesia(self, aspire_raw: pd.DataFrame) -> pd.DataFrame:
        for _, row in aspire_raw.iterrows():
            name = row.get("Name") or ""
            city = row.get("Normalized City") or ""
            query = f"{name}, {city}"

            res = get_location_geocoding(address=query)

            rows = []
            if not res:
                continue
            if isinstance(res, list) and len(res) > 0:
                location_type = res[0].get("granularity", "APPROXIMATE")
                place_id = res[0].get("placeId")
            elif isinstance(res, str):
                location_type = "ROOFTOP"
                place_id = res
            else:
                continue
            if place_id:
                rows.append(
                    {
                        "customerName": row["customerName"],
                        "place_id": str(place_id),
                        "location_type": str(location_type),
                    }
                )

        if rows:
            gcs_paths = [f"{MATCHING_DATASET_FOLDER_NAME}/place-id-details/df_aspire_id.csv"]
            geoc = self.downloader.download_csv_files(gcs_paths=gcs_paths)
            geoc = pd.read_csv(io.BytesIO(geoc[gcs_paths[0]])) if gcs_paths[0] in geoc else pd.DataFrame()
            new_df = pd.DataFrame(rows)
            all_df = pd.concat([geoc, new_df], ignore_index=True) if not geoc.empty else new_df
            all_df = all_df.drop_duplicates(subset=["customerName"], keep="last")
            response = self.uploader.upload_dataframe(
                df=all_df,
                gcs_path=gcs_paths[0],
            )

            if len(response.get("successful")) > 0:
                print(f"Uploaded geocoding.csv with {len(all_df)} rows")
            else:
                print("Failed to upload geocoding.csv")

            LOGGER.info("Geocoded and appended %d rows", len(new_df))
        else:
            LOGGER.info("No new geocoding rows to append")

    def run(self, aspire_raw: pd.DataFrame, gmaps_details: pd.DataFrame, city: str = "city is empty") -> pd.DataFrame:
        if aspire_raw.empty:
            raise FileNotFoundError(f"Aspire {city} is missing/empty")
        aspire_raw["customerCode"] = aspire_raw["customerCode"].map(safe_convert_customer_code)

        if not gmaps_details.empty and "Unnamed: 0.4" in gmaps_details.columns:
            gmaps_details = gmaps_details.drop(columns=["Unnamed: 0.4"], errors="ignore")

        gmaps_details = gmaps_details[gmaps_details.get("name").notna()] if not gmaps_details.empty else gmaps_details

        gmaps_details = (
            gmaps_details.drop_duplicates(subset=["id"], keep="last") if not gmaps_details.empty else gmaps_details
        )

        matching = aspire_raw.copy()
        matching["gmaps_id"] = np.nan
        matching["customerCode"] = matching["customerCode"].map(safe_convert_customer_code)

        df_latlon = matching_lat_lon(
            aspire_data=aspire_raw,
            gmaps_data=gmaps_details,
            max_distance=max_distance_m,
        )

        df_latlon = fuzzy_matching_name(df=df_latlon)
        df_latlon = df_latlon[(df_latlon["fuzzy_rank"] == 1) & (df_latlon["fuzzy_score"] >= fuzzy_min_score)]
        latlon_map = df_latlon.set_index("customerCode")["id"]
        latlon_mask = matching["customerCode"].isin(latlon_map.index)
        matching.loc[latlon_mask, "matching_step"] = "lat/lon"
        matching.loc[latlon_mask, "gmaps_id"] = matching.loc[latlon_mask, "customerCode"].map(latlon_map)
        print("Lat/Lon matched: %d (%.2f%%)", len(df_latlon), 100 * len(df_latlon) / max(len(aspire_raw), 1))

        remain = matching[matching["matching_step"].isna()].copy()
        print(f"Remaining after lat/lon: {len(remain)}")
        df_addr = address_matching(remain, df_gmaps_sg=gmaps_details)
        df_addr = fuzzy_matching_name(df=df_addr)
        df_addr = df_addr[(df_addr["fuzzy_rank"] == 1) & (df_addr["fuzzy_score"] >= fuzzy_min_score)]
        df_addr = df_addr.sort_values("fuzzy_score", ascending=False).drop_duplicates("customerCode", keep="last")
        addr_map = df_addr.set_index("customerCode")["id"]
        addr_mask = matching["gmaps_id"].isna() & matching["customerCode"].isin(addr_map.index)
        matching.loc[addr_mask, "matching_step"] = "address"
        matching.loc[addr_mask, "gmaps_id"] = matching.loc[addr_mask, "customerCode"].map(addr_map)
        print(
            "Address matched: %d of remain (%.2f%% of remain)", len(df_addr), 100 * len(df_addr) / max(len(remain), 1)
        )

        remain = matching[matching["matching_step"].isna()].copy()
        print(f"Remaining after address: {len(remain)}")

        geocoding_path = f"{MATCHING_DATASET_FOLDER_NAME}/geocoding-matching/geocoding.csv"
        geoc = self.downloader.download_csv_files(gcs_paths=[geocoding_path])
        geoc = pd.read_csv(io.BytesIO(geoc[geocoding_path]))

        geoc["customerCode"] = geoc["customerCode"].map(safe_convert_customer_code)
        geoc.drop_duplicates("customerCode", keep="last", inplace=True)
        remain = remain.merge(geoc, on=["customerCode"], how="left")
        remain = remain[remain["place_id"].isna()].copy()
        print(f"Geocoding missing place_id for {len(remain)} rows")
        if not remain.empty:
            self._geocode_missing(remain)

            geoc = self.downloader.download_csv_files(gcs_paths=[geocoding_path])
            geoc = pd.read_csv(io.BytesIO(geoc[geocoding_path]))

            if geoc.empty:
                LOGGER.info("No geocoding rows available; skipping downstream place-id joins.")
            else:
                geoc["customerCode"] = geoc["customerCode"].map(safe_convert_customer_code)
                geoc = geoc.drop_duplicates("customerCode", keep="last")

                remain = matching[matching["matching_step"].isna()].copy()
                joined = remain.merge(geoc, on="customerCode", how="left")
                no_pid = joined[joined["place_id"].isnull()]["customerCode"]
                matching.loc[matching["customerCode"].isin(no_pid), "matching_step"] = "no_place_id"

                has_pid = joined[joined["place_id"].notna()].copy()

                place_join = has_pid.merge(
                    gmaps_details, left_on="place_id", right_on="id", how="left"
                ).drop_duplicates("customerCode")

                pid_ok = place_join[place_join["id"].notna()]
                matching.loc[matching["customerCode"].isin(pid_ok["customerCode"]), "matching_step"] = (
                    "join_with_place_id"
                )
                pid_map = pid_ok.set_index("customerCode")["id"]
                mask = matching["customerCode"].isin(pid_map.index)
                matching.loc[mask, "gmaps_id"] = matching.loc[mask, "customerCode"].map(pid_map)

        LOGGER.info("matching_step distribution:\n%s", matching["matching_step"].value_counts(dropna=False).to_string())

        self.uploader.upload_dataframe(
            df=matching,
            gcs_path=f"{MATCHING_DATASET_FOLDER_NAME}/matching-result-raw/{city}_matching_result.csv",
        )

        return matching

    def run_non_latin(
        self, aspire_raw: pd.DataFrame, gmaps_details: pd.DataFrame, city: str = "city is empty"
    ) -> pd.DataFrame:
        if aspire_raw.empty:
            raise FileNotFoundError(f"Aspire {city} is missing/empty")
        aspire_raw["customerCode"] = aspire_raw["customerCode"].map(safe_convert_customer_code)

        if not gmaps_details.empty and "Unnamed: 0.4" in gmaps_details.columns:
            gmaps_details = gmaps_details.drop(columns=["Unnamed: 0.4"], errors="ignore")

        gmaps_details = gmaps_details[gmaps_details.get("name").notna()] if not gmaps_details.empty else gmaps_details

        gmaps_details = (
            gmaps_details.drop_duplicates(subset=["id"], keep="last") if not gmaps_details.empty else gmaps_details
        )

        matching = aspire_raw.copy()
        matching["gmaps_id"] = np.nan
        matching["customerCode"] = matching["customerCode"].map(safe_convert_customer_code)

        df_latlon = matching_lat_lon(
            aspire_data=aspire_raw,
            gmaps_data=gmaps_details,
            max_distance=max_distance_m,
        )

        df_latlon = embedding_matching(aspire_match=df_latlon)
        df_latlon["final"] = df_latlon.apply(lambda row: row["sim"] * 0.8 + row["place"] * 0.2, axis=1)
        df_latlon = (
            df_latlon[df_latlon["final"] >= 0.6]
            .sort_values(["final"], ascending=False)
            .drop_duplicates("customerCode", keep="first")
        )

        latlon_map = df_latlon.set_index("customerCode")["id"]
        latlon_mask = matching["customerCode"].isin(latlon_map.index)
        matching.loc[latlon_mask, "matching_step"] = "lat/lon"
        matching["gmaps_id"] = matching["gmaps_id"].fillna(matching["customerCode"].map(latlon_map))

        matching.loc[latlon_mask, "matching_step"] = "lat/lon"
        matching.loc[latlon_mask, "gmaps_id"] = matching.loc[latlon_mask, "customerCode"].map(latlon_map)
        print("Lat/Lon matched: %d (%.2f%%)", len(df_latlon), 100 * len(df_latlon) / max(len(aspire_raw), 1))

        remain = matching[matching["matching_step"].isna()].copy()
        print(f"Remaining after lat/lon: {len(remain)}")

        df_addr = match_tables(
            remain[remain["customerAddress"].notna()],
            gmaps_details,
            threshold=0.80,
            internal_name_col="Name",
            internal_addr_col="customerAddress",
            external_name_col="displayName_text",
            external_addr_col="formattedAddress",
            batch_size=32,
        )

        addr_map = df_addr.set_index("int_customerCode")["ext_id"]
        addr_mask = matching["gmaps_id"].isna() & matching["customerCode"].isin(addr_map.index)
        matching.loc[addr_mask, "matching_step"] = "address"
        matching.loc[addr_mask, "gmaps_id"] = matching.loc[addr_mask, "customerCode"].map(addr_map)
        print(
            "Address matched: %d of remain (%.2f%% of remain)", len(df_addr), 100 * len(df_addr) / max(len(remain), 1)
        )

        remain = matching[matching["matching_step"].isna()].copy()
        print(f"Remaining after address: {len(remain)}")

        geocoding_path = f"{MATCHING_DATASET_FOLDER_NAME}/geocoding-matching/all_place_id_non_alpha.csv"
        geoc = self.downloader.download_csv_files(gcs_paths=[geocoding_path])
        geoc = pd.read_csv(io.BytesIO(geoc[geocoding_path]))

        geoc["customerCode"] = geoc["customerCode"].map(safe_convert_customer_code)
        geoc.drop_duplicates("customerCode", keep="last", inplace=True)
        remain = remain.merge(geoc, on=["customerCode"], how="left")
        remain = remain[remain["place_id"].isna()].copy()
        print(f"Geocoding missing place_id for {len(remain)} rows")
        if not remain.empty:
            self._geocode_missing_for_non_latin(remain)

            geoc = self.downloader.download_csv_files(gcs_paths=[geocoding_path])

            geoc = pd.read_csv(io.BytesIO(geoc[geocoding_path]))
            if geoc.empty:
                LOGGER.info("No geocoding rows available; skipping downstream place-id joins.")
            else:
                geoc["customerCode"] = geoc["customerCode"].map(safe_convert_customer_code)
                geoc = geoc.drop_duplicates("customerCode", keep="last")

                remain = matching[matching["matching_step"].isna()].copy()
                joined = remain.merge(geoc, on="customerCode", how="left")
                no_pid = joined[joined["place_id"].isnull()]["customerCode"]
                matching.loc[matching["customerCode"].isin(no_pid), "matching_step"] = "no_place_id"

                has_pid = joined[joined["place_id"].notna()].copy()

                place_join = has_pid.merge(
                    gmaps_details, left_on="place_id", right_on="id", how="left"
                ).drop_duplicates("customerCode")

                res = embedding_matching(place_join)
                res["final"] = res.apply(lambda row: row["sim"] * 0.6 + row["place"] * 0.4, axis=1)
                place_join = res[res["final"] > 0.4]

                pid_ok = place_join[place_join["id"].notna()]
                matching.loc[matching["customerCode"].isin(pid_ok["customerCode"]), "matching_step"] = (
                    "join_with_place_id"
                )
                pid_map = pid_ok.set_index("customerCode")["id"]
                mask = matching["customerCode"].isin(pid_map.index)
                matching.loc[mask, "gmaps_id"] = matching.loc[mask, "customerCode"].map(pid_map)

        self.uploader.upload_dataframe(
            df=matching,
            gcs_path=f"{MATCHING_DATASET_FOLDER_NAME}/matching-result-raw/{city}_matching_result.csv",
        )

        LOGGER.info("matching_step distribution:\n%s", matching["matching_step"].value_counts(dropna=False).to_string())
        return matching
