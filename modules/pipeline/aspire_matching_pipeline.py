import io

import pandas as pd

from config.gcs import (
    ASPIRE_DATASET_FOLDER_NAME,
    GOOGLE_DATA_EXTRACTION_FOLDER_NAME,
    MATCHING_DATASET_FOLDER_NAME,
    TRAINING_DATASET_FOLDER_NAME,
    UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME,
)
from config.parameters import SHP_CITIES, region_country_code_mapping
from modules.google_cloud_storage.downloader import GCSDownloader
from modules.google_cloud_storage.uploader import GCSUploader
from modules.google_maps.utils import flatten_universe_column
from modules.matching.matching_pipeline import MatchingPipeline
from modules.pipeline.aspire_dataset_extraction_pipeline import (
    AspireDatasetExtractionPipeline,
)


class AspireMappingPipeline:
    def __init__(self, env: str = "prd"):
        self.env = env
        self.uploader = GCSUploader()
        self.downloader = GCSDownloader()
        self.matching_pipeline = MatchingPipeline()
        self.aspire_data_extraction_pipeline = AspireDatasetExtractionPipeline()
        self.matching = None

    def get_latest_google_data_extraction(self):
        if self.env == "prd":
            prefix = f"{GOOGLE_DATA_EXTRACTION_FOLDER_NAME}/"
            self.latest_date = self.downloader.get_folder_list(prefix)[0]

            gcs_path = self.latest_date + "combined/data-extraction.csv"

            file_bytes = self.downloader.download_csv_files(gcs_paths=[gcs_path])
            raw_universe_data = pd.read_csv(io.BytesIO(file_bytes[gcs_path]))

            self.raw_universe_data = flatten_universe_column(raw_universe_data)
            self.raw_universe_data.drop_duplicates(subset="id", inplace=True)

            if "postalAddress_regionCode" in self.raw_universe_data.columns:
                self.raw_universe_data = self.raw_universe_data[
                    self.raw_universe_data.apply(
                        lambda row: (
                            region_country_code_mapping.get(row["extractionCountryCode"], None)
                            == row["postalAddress_regionCode"]
                            or pd.isna(row["postalAddress_regionCode"])
                        ),
                        axis=1,
                    )
                ]
            else:
                pass

            res = self.uploader.upload_dataframe(
                df=self.raw_universe_data, gcs_path=f"{UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME}/data-extraction.csv"
            )
        elif self.env == "dev":
            gcs_path = [f"{UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME}/data-extraction.csv"]
            file_bytes = self.downloader.download_csv_files(gcs_paths=gcs_path)
            self.raw_universe_data = pd.read_csv(io.BytesIO(file_bytes[gcs_path[0]]))

    def get_aspire_dataset(self):
        gcs_path = [
            f"{ASPIRE_DATASET_FOLDER_NAME}/aspire_customers_for_mapping.csv",
        ]
        file_bytes = self.downloader.download_csv_files(gcs_paths=gcs_path)
        self.aspire_customers_df = pd.read_csv(io.BytesIO(file_bytes[gcs_path[0]]))

        self.aspire_customers_df = self.aspire_customers_df[
            (
                (self.aspire_customers_df["is_high_energy"])
                & (self.aspire_customers_df["InSingleSourceOfTruth"])
                & (~self.aspire_customers_df["legal_entity_name_only"])
            )
            | (
                (~self.aspire_customers_df["is_high_energy"])
                & (~self.aspire_customers_df["closed_in_title"])
                & (self.aspire_customers_df["in_scope"])
                & (~self.aspire_customers_df["legal_entity_name_only"])
                & (self.aspire_customers_df["has_sales_after_2023"])
            )
        ]

    def get_matching_indo(self):
        self.indonesia_customers_df = self.aspire_data_extraction_pipeline.get_indonesia_dataset()

        gcs_path = [f"matching-dataset/place-id-details/df_aspire_id.csv"]
        file_bytes = self.downloader.download_csv_files(gcs_paths=gcs_path)
        indo = pd.read_csv(io.BytesIO(file_bytes[gcs_path[0]]))
        indo["place_id"].fillna("not available", inplace=True)

        self.indonesia_customers_df = self.indonesia_customers_df.merge(
            indo[["customerName", "place_id"]], on="customerName", how="left"
        )
        remain = self.indonesia_customers_df[self.indonesia_customers_df["place_id"].isna()]

        if remain.shape[0] > 0:
            self.matching_pipeline.run_matching_for_indonesia(remain)
            file_bytes = self.downloader.download_csv_files(gcs_paths=gcs_path)
            indo = pd.read_csv(io.BytesIO(file_bytes[gcs_path[0]]))
            self.indonesia_customers_df = self.indonesia_customers_df.drop(columns=["place_id"], axis=1).merge(
                indo[["customerName", "place_id"]], on="customerName", how="left"
            )

        self.indonesia_customers_df.rename(columns={"place_id": "gmaps_id"}, inplace=True)

    def get_matching(self, city: str, country_type: str):
        df_aspire_data = self.aspire_customers_df[self.aspire_customers_df["Normalized City"] == city]

        if df_aspire_data.shape[0] == 0:
            print(f"No Aspire data for {city}")
            return

        df_google_maps = self.raw_universe_data[
            self.raw_universe_data["extractionCities"] == SHP_CITIES[city].get("city")
        ]

        if df_google_maps.shape[0] == 0:
            print(f"No Google Maps data for {city}")
            return

        if country_type == "latin":
            self.matching = self.matching_pipeline.run(
                city=city, aspire_raw=df_aspire_data, gmaps_details=df_google_maps
            )
        elif country_type == "non-latin":
            self.matching = self.matching_pipeline.run_non_latin(
                city=city, aspire_raw=df_aspire_data, gmaps_details=df_google_maps
            )
        else:
            raise ValueError(f"Unknown country type: {country_type}")

    def match_all_cities(self):
        for city in SHP_CITIES.keys():
            self.get_matching(city=city, country_type=SHP_CITIES[city].get("country_type"))

    def matching_finalize(self):
        self.get_matching_indo()

        paths = self.downloader.get_file_list(f"{MATCHING_DATASET_FOLDER_NAME}/matching-result-raw/")
        filebytes = self.downloader.download_csv_files(paths)

        matching_result_raw = pd.DataFrame()
        for path in paths:
            match = pd.read_csv(io.BytesIO(filebytes[path]))
            matching_result_raw = pd.concat([matching_result_raw, match], ignore_index=True)

        training_data = pd.concat(
            [
                matching_result_raw[["gmaps_id", "is_high_energy"]].merge(
                    self.raw_universe_data, left_on="gmaps_id", right_on="id", how="left"
                ),
                self.indonesia_customers_df[["gmaps_id", "is_high_energy"]].merge(
                    self.raw_universe_data, left_on="gmaps_id", right_on="id", how="left"
                ),
            ]
        )

        self.uploader.upload_dataframe(
            df=training_data,
            gcs_path=f"{TRAINING_DATASET_FOLDER_NAME}/training_data.csv",
        )
