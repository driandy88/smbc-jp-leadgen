import pickle
from io import BytesIO

import numpy as np
import pandas as pd

from config.gcs import (
    ASPIRE_DATASET_FOLDER_NAME,
    MATCHING_DATASET_FOLDER_NAME,
    MODEL_FOLDER_NAME,
    TRAINING_DATASET_FOLDER_NAME,
    UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME,
)
from config.models import ML_FEATURE_COLS, boolean_features, mapping_bool
from modules.google_cloud_storage.downloader import GCSDownloader
from modules.google_cloud_storage.uploader import GCSUploader
from modules.model.features_processing import (
    features_prep,
    preprocess_features,
    price_level_map,
)
from modules.pipeline.training_and_backtest_pipeline import BackTestPipeline


class InferencePipeline:
    def __init__(self, env="prd"):
        self.downloader = GCSDownloader()
        model_bytes = self.downloader.download_csv(gcs_path=f"{MODEL_FOLDER_NAME}/model.pkl")
        self.model = pickle.loads(model_bytes)
        self.backtest_pipeline = BackTestPipeline()
        self.backtest_pipeline.load_training_testing_data()
        self.env = env

    def load_universe_data(self):
        """
        Load universe data from GCS.
        """
        if self.env == "prd":
            gcs_paths = [
                f"{UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME}/data-extraction.csv",
                f"{MATCHING_DATASET_FOLDER_NAME}/complete_result/matching_data.csv",
                f"{ASPIRE_DATASET_FOLDER_NAME}/ManualReviewMasterData VF - List of Doors.csv",
                f"{UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME}/high_energy_not_in_universe.csv",
            ]
        elif self.env == "dev":
            gcs_paths = [
                f"{TRAINING_DATASET_FOLDER_NAME}/data-extraction-sample.csv",
                f"{MATCHING_DATASET_FOLDER_NAME}/complete_result/matching_data.csv",
                f"{ASPIRE_DATASET_FOLDER_NAME}/ManualReviewMasterData VF - List of Doors.csv",
                f"{UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME}/high_energy_not_in_universe.csv",
            ]

        universe_data_bytes = self.downloader.download_csv_files(gcs_paths=gcs_paths)

        self.universe_data = pd.read_csv(BytesIO(universe_data_bytes[gcs_paths[0]]))
        self.matching_data = pd.read_csv(BytesIO(universe_data_bytes[gcs_paths[1]]))
        self.manual_review = pd.read_csv(BytesIO(universe_data_bytes[gcs_paths[2]]))
        self.additional_universe = pd.read_csv(BytesIO(universe_data_bytes[gcs_paths[3]]))

        self.universe_data = pd.concat(
            [self.universe_data, self.additional_universe], ignore_index=True
        ).drop_duplicates(subset=["id"])

    def run_inference(self):
        X_train = self.backtest_pipeline.dataframes["X_train"]
        for col in boolean_features:
            X_train[col] = X_train[col].map(mapping_bool)
            self.universe_data[col] = self.universe_data[col].map(mapping_bool)

        print("Starting feature preparation...")
        universe_data = features_prep([self.universe_data])[0]
        X_train = features_prep([X_train])[0]
        universe_data = universe_data[ML_FEATURE_COLS]
        X_train = X_train[ML_FEATURE_COLS]
        print("Feature preparation completed.")

        print("Starting feature preprocessing...")

        X_train = preprocess_features(X_train, price_level_map, ML_FEATURE_COLS)
        universe_data = preprocess_features(
            universe_data, price_level_map, ML_FEATURE_COLS, fit_columns=X_train.columns
        )
        print("Feature preprocessing completed.")

        print("Running model inference...")
        proba = self.model.predict_proba(universe_data)[:, 1]
        universe_data["proba"] = proba
        print("Model inference completed.")

        print("Binning probabilities...")
        bin_edges = np.arange(0, 1.01, 0.1)
        bin_labels = [f"{bin_edges[i]:.1f}-{bin_edges[i + 1]:.1f}" for i in range(len(bin_edges) - 1)]
        universe_data["proba_bin"] = pd.cut(
            universe_data["proba"], bins=bin_edges, labels=bin_labels, include_lowest=True
        )
        print("Binning completed.")

        self.universe_data["proba"] = universe_data["proba"]
        self.universe_data["proba_bin"] = universe_data["proba_bin"]
        print("Inference results added to universe_data.")

    def post_processing(self):
        """
        Perform post-processing on the universe data.
        This could include filtering, sorting, or any other necessary steps.
        """
        print("Loading training and testing data for post-processing...")

        self.backtest_pipeline.load_training_testing_data()
        X_train = self.backtest_pipeline.dataframes["X_train"]
        X_test = self.backtest_pipeline.dataframes["X_test"]
        y_train = self.backtest_pipeline.dataframes["y_train"]
        y_test = self.backtest_pipeline.dataframes["y_test"]

        print("Concatenating training and testing data...")
        X_train_temp = pd.concat([X_train, y_train], axis=1)
        X_test_temp = pd.concat([X_test, y_test], axis=1)

        print("Marking Aspire data in training and testing sets...")
        X_train_temp.loc[X_train_temp["source"] == "manual_review", "Is_manualreview_training_data"] = True
        X_test_temp.loc[X_test_temp["source"] == "manual_review", "Is_manualreview_testing_data"] = True
        X_train_temp.loc[X_train_temp["source"] == "Aspire", "Is_Aspire_data"] = True
        X_test_temp.loc[X_test_temp["source"] == "Aspire", "Is_Aspire_data"] = True

        X_train_temp.loc[X_train_temp["source"] == "Aspire", "Is_aspire_training_data"] = True
        X_test_temp.loc[X_test_temp["source"] == "Aspire", "Is_aspire_testing_data"] = True

        print("Combining and deduplicating training and testing data...")
        X_copy = pd.concat(
            [
                X_train_temp[["id", "Is_aspire_training_data", "Is_manualreview_training_data"]],
                X_test_temp[["id", "Is_aspire_testing_data", "Is_manualreview_testing_data"]],
            ]
        )

        X_copy.drop_duplicates(subset=["id"], inplace=True)

        print("Merging matching data with universe data...")
        self.manual_review = self.manual_review.merge(
            self.universe_data[["googleMapsUri", "id"]], on="googleMapsUri", how="left"
        )

        self.manual_review.rename(
            columns={
                "Pierre HE review": "Is_HE_manual_review",
                "Manual Review Model": "Is_manual_review",
                "Type of HE Venue": "Channel_from_Pierre",
                "Brandbuilding Capacity": "Brand_building_capacity_from_Pierre",
            },
            inplace=True,
        )

        self.matching_data = self.matching_data.merge(
            self.universe_data[["googleMapsUri", "id"]],
            on="googleMapsUri",
            how="left",
        )

        print("Setting Aspire flags in matching data...")
        self.matching_data["Is_Aspire_data"] = True
        self.matching_data.loc[self.matching_data["is_high_energy"], "Is_Aspire_HE"] = True
        self.matching_data.loc[~self.matching_data["is_high_energy"], "Is_Aspire_HE"] = False

        print("Merging all datasets for post-processing...")
        all_dataset_complete = (
            self.universe_data[
                [
                    "id",
                    "googleMapsUri",
                    "extractionCountryCode",
                    "extractionCities",
                    "businessStatus",
                    "displayName_text",
                    "formattedAddress",
                    "proba",
                    "proba_bin",
                    "userRatingCount",
                    "primaryType",
                    "priceLevel",
                ]
            ]
            .merge(X_copy, left_on="id", right_on="id", how="left")
            .merge(
                self.matching_data[["gmaps_id", "Is_Aspire_data", "Is_Aspire_HE"]],
                right_on="gmaps_id",
                left_on="id",
                how="left",
            )
            .merge(
                self.manual_review[
                    [
                        "id",
                        "Is_HE_manual_review",
                        "Is_manual_review",
                        "Brand_building_capacity_from_Pierre",
                        "Channel_from_Pierre",
                    ]
                ],
                on=["id"],
                how="left",
            )
        )

        all_dataset_complete.drop(columns=["gmaps_id"], inplace=True)

        print("Applying exclusion rules for post-processing...")
        all_dataset_complete.loc[
            all_dataset_complete["primaryType"].str.contains(
                "supermarket|massage|office|shop|touristic spot|tourist|beach|sports_club", case=False, na=False
            ),
            "is_excluded_from_Post_Processing",
        ] = True
        all_dataset_complete.loc[all_dataset_complete["userRatingCount"] < 5, "is_excluded_from_Post_Processing"] = True
        all_dataset_complete.loc[
            (all_dataset_complete["priceLevel"] == "PRICE_LEVEL_INEXPENSIVE")
            & (~all_dataset_complete["primaryType"].str.contains("bar|nightclub", case=False, na=False)),
            "is_excluded_from_Post_Processing",
        ] = True

        print("Filling missing values for boolean columns...")
        for col in [
            "Is_Aspire_data",
            "Is_aspire_training_data",
            "Is_aspire_testing_data",
            "Is_manualreview_training_data",
            "Is_manualreview_testing_data",
            "is_excluded_from_Post_Processing",
        ]:
            all_dataset_complete[col] = all_dataset_complete[col].fillna(False)

        print("Post-processing completed.")
        all_dataset_complete["Is_manual_review"].fillna("Not Reviewed", inplace=True)

        all_dataset_complete.loc[all_dataset_complete["Is_manual_review"] == "Not Reviewed", "Final_Combined_HE"] = (
            "Not Reviewed"
        )
        all_dataset_complete.loc[
            (~all_dataset_complete["Is_Aspire_HE"].fillna(False))
            | (~all_dataset_complete["Is_HE_manual_review"].fillna(False)),
            "Final_Combined_HE",
        ] = False
        all_dataset_complete.loc[
            (~all_dataset_complete["Is_HE_manual_review"].fillna(False))
            | (all_dataset_complete["Is_Aspire_HE"].fillna(False)),
            "Final_Combined_HE",
        ] = True

        self.all_dataset_complete = all_dataset_complete

    def save_results(self):
        """
        Save the processed results back to GCS.
        """
        uploader = GCSUploader()
        output_csv = "post_processed_universe_data.csv"
        uploader.upload_dataframe(
            df=self.all_dataset_complete, gcs_path=f"{UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME}/{output_csv}"
        )
