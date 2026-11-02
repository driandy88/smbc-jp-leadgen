import io
import re
from io import BytesIO

import numpy as np
import pandas as pd

from config.gcs import ASPIRE_DATASET_FOLDER_NAME
from config.parameters import RELEVANT_CHANNEL_LIST, legal_entity_suffix
from modules.google_cloud_storage.bigquery_loader import (
    load_aspire_customers_table_custom_query,
    load_aspire_sales_table,
)
from modules.google_cloud_storage.downloader import GCSDownloader
from modules.google_cloud_storage.uploader import GCSUploader


class AspireDatasetExtractionPipeline:
    def __init__(self):
        self.aspire_customers_df = None
        self.downloader = GCSDownloader()
        self.uploader = GCSUploader()
        self.source_of_truth_df = None

    def retrieve_aspire_table(self) -> pd.DataFrame:
        """Run the Aspire dataset extraction pipeline."""
        self.aspire_customers_df = load_aspire_customers_table_custom_query()
        self.sales_after_2023_df = load_aspire_sales_table()

    def retrieve_additional_tables(self) -> pd.DataFrame:
        """Retrieve the Aspire customers source of truth dataset."""
        gcs_paths = [
            f"{ASPIRE_DATASET_FOLDER_NAME}/source-of-truth/aspire_he_source_of_truth.csv",
            f"{ASPIRE_DATASET_FOLDER_NAME}/source-of-truth/Channel List - 2024.08.03 - city_name_all.csv",
        ]

        byte_files = self.downloader.download_csv_files(gcs_paths=gcs_paths)

        self.source_of_truth_df = pd.read_csv(BytesIO(byte_files[gcs_paths[0]]))
        self.city_mapping = pd.read_csv(BytesIO(byte_files[gcs_paths[1]]))

        self.city_mapping = self.city_mapping[
            (self.city_mapping["customerCity.1"].isin(["Included", "Empty"])) & (self.city_mapping["total"] > 0)
        ]

    def get_aspire_table_clean(self) -> pd.DataFrame:
        self.aspire_customers_df["InSingleSourceOfTruth"] = False

        self.aspire_customers_df.loc[
            (self.aspire_customers_df["is_high_energy"])
            & (self.aspire_customers_df["customerCode"].isin(self.source_of_truth_df["customerCode"].values)),
            "InSingleSourceOfTruth",
        ] = True

        pd.concat(
            [
                self.aspire_customers_df[
                    (self.aspire_customers_df["is_high_energy"])
                    & (self.aspire_customers_df["customerCode"].isin(self.source_of_truth_df["customerCode"].values))
                ],
                self.aspire_customers_df[~(self.aspire_customers_df["is_high_energy"])],
            ]
        )

        self.aspire_customers_df = self.aspire_customers_df[
            (self.aspire_customers_df["channel"].isin(RELEVANT_CHANNEL_LIST))
        ]
        self.aspire_customers_df = self.aspire_customers_df.merge(
            self.city_mapping, on=["customerCity", "salesforceCustomerCountryCode"], how="left"
        ).drop(["NON HE", "HE", "total"], axis=1)

    def check_name_contains_legal_entity_name_only(self) -> pd.DataFrame:
        self.aspire_customers_df["containsLegalEntityName"] = self.aspire_customers_df.apply(
            lambda x: True
            in [
                suffix.lower() in x["customerName"].lower()
                for suffix in legal_entity_suffix.get(
                    x["salesAreaName"]
                    if pd.isna(x["salesforceCustomerCountryCode"])
                    else x["salesforceCustomerCountryCode"],
                    [],
                )
            ],
            axis=1,
        )

        self.aspire_customers_df["containsLegalEntityName2"] = self.aspire_customers_df.apply(
            lambda x: (
                False
                if pd.isnull(x["customerName2"]) or pd.isnull(x["salesforceCustomerCountryCode"])
                else any(
                    suffix.lower() in x["customerName2"].lower()
                    for suffix in legal_entity_suffix.get(x["salesforceCustomerCountryCode"], [])
                )
            ),
            axis=1,
        )
        self.aspire_customers_df["containsLegalEntityLocalName"] = self.aspire_customers_df.apply(
            lambda x: (
                False
                if pd.isnull(x["salesforceLocalName"]) or pd.isnull(x["salesforceCustomerCountryCode"])
                else any(
                    suffix.lower() in x["salesforceLocalName"].lower()
                    for suffix in legal_entity_suffix.get(x["salesforceCustomerCountryCode"], [])
                )
            ),
            axis=1,
        )

        self.aspire_customers_df["Name"] = self.aspire_customers_df.apply(
            lambda row: row["salesforceLocalName"]
            if (not row["containsLegalEntityLocalName"] and pd.notna(row["salesforceLocalName"]))
            else row["customerName2"]
            if (not row["containsLegalEntityName2"] and pd.notna(row["customerName2"]))
            else row["customerName"]
            if (not row["containsLegalEntityName"])
            else np.nan,
            axis=1,
        )

        self.aspire_customers_df["legal_entity_name_only"] = self.aspire_customers_df["Name"].isna()

    def check_close_in_title(self) -> pd.DataFrame:
        self.aspire_customers_df["closed_in_title"] = self.aspire_customers_df[
            ["customerName", "customerName2", "salesforceLocalName"]
        ].apply(
            lambda row: "closed"
            in (
                str(row["customerName"]) + " " + str(row["customerName2"]) + " " + str(row["salesforceLocalName"])
            ).lower(),
            axis=1,
        )

    def check_in_scope(self) -> pd.DataFrame:
        self.aspire_customers_df["in_scope"] = self.aspire_customers_df["customerCity.1"].notna()

    def check_has_sales_after_2023(self) -> pd.DataFrame:
        self.aspire_customers_df["has_sales_after_2023"] = self.aspire_customers_df.customerCode.isin(
            self.sales_after_2023_df.account_id
        )

    def run_pipeline(self) -> pd.DataFrame:
        """Run the Aspire dataset extraction pipeline."""
        self.retrieve_aspire_table()
        self.retrieve_additional_tables()
        self.get_aspire_table_clean()
        self.check_name_contains_legal_entity_name_only()
        self.check_close_in_title()
        self.check_in_scope()
        self.check_has_sales_after_2023()

        self.uploader.upload_dataframe(
            self.aspire_customers_df,
            f"{ASPIRE_DATASET_FOLDER_NAME}/aspire_customers_for_mapping.csv",
        )

    def get_indonesia_dataset(self):
        gcs_path = [
            f"{ASPIRE_DATASET_FOLDER_NAME}/Indonesia HE segmentation.csv",
        ]
        file_bytes = self.downloader.download_csv_files(gcs_paths=gcs_path)
        self.indonesia_customers_df = pd.read_csv(io.BytesIO(file_bytes[gcs_path[0]]))
        self.indonesia_customers_df = self.indonesia_customers_df[
            self.indonesia_customers_df["Sales area"].isin(["Jakarta", "Bali", "Surabaya", "Medan"])
        ]
        self.indonesia_customers_df = self.indonesia_customers_df[
            ~self.indonesia_customers_df["Channel"].isin(["On - Restaurants", "On - Show Venue"])
        ]

        PARENS_RX = re.compile(r"\(([^)]+)\)")
        self.indonesia_customers_df["Name"] = self.indonesia_customers_df.apply(
            lambda x: (x["Venues High Energy Indonesia"]).split("-")[-1]
            if ("-" in x["Venues High Energy Indonesia"] and "PT" in x["Venues High Energy Indonesia"])
            else "MAMAKA BY OVOLO"
            if "MAMAKA BY OVOLO" in x["Venues High Energy Indonesia"]
            else "LOCCA BEACH CLUB"
            if "LOCCA BEACH CLUB" in x["Venues High Energy Indonesia"]
            else PARENS_RX.findall(x["Venues High Energy Indonesia"])[0]
            if (
                "(" in x["Venues High Energy Indonesia"]
                and len(PARENS_RX.findall(x["Venues High Energy Indonesia"])) > 0
            )
            else x["Venues High Energy Indonesia"],
            axis=1,
        )

        self.indonesia_customers_df["containsLegalEntityName"] = self.indonesia_customers_df.apply(
            lambda x: True in [suffix.lower() in x["Name"].lower() for suffix in legal_entity_suffix["Indonesia"]],
            axis=1,
        )

        self.indonesia_customers_df = self.indonesia_customers_df.rename(
            columns={
                "Venues High Energy Indonesia": "customerName",
                "Sales area": "Normalized City",
                "High Energy or not?": "salesforceOnAttributes",
                "Channel": "subchannelName",
            }
        )

        self.indonesia_customers_df.loc[
            self.indonesia_customers_df["salesforceOnAttributes"] == "HE", "is_high_energy"
        ] = True
        self.indonesia_customers_df.loc[
            (self.indonesia_customers_df["salesforceOnAttributes"] != "HE"), "is_high_energy"
        ] = False
        return self.indonesia_customers_df
