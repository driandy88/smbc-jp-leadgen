import os
import tempfile

import joblib
import pandas as pd

from config.gcs import MODEL_FOLDER_NAME, TRAINING_DATASET_FOLDER_NAME
from config.models import ML_FEATURE_COLS, boolean_features, mapping_bool
from modules.google_cloud_storage.downloader import GCSDownloader
from modules.google_cloud_storage.uploader import GCSUploader
from modules.model.features_processing import (
    features_prep,
    preprocess_features,
    price_level_map,
)
from modules.model.machine_learning import ml_experiment


class BackTestPipeline:
    def __init__(self):
        self.downloader = GCSDownloader()
        self.uploader = GCSUploader()

    def load_training_testing_data(self):
        list_of_dataset = self.downloader.download_csv_files(
            gcs_paths=[
                f"{TRAINING_DATASET_FOLDER_NAME}/X_train.csv",
                f"{TRAINING_DATASET_FOLDER_NAME}/X_test.csv",
                f"{TRAINING_DATASET_FOLDER_NAME}/y_train.csv",
                f"{TRAINING_DATASET_FOLDER_NAME}/y_test.csv",
            ]
        )
        self.dataframes = {}
        for path, file_bytes in list_of_dataset.items():
            self.dataframes[path.split("/")[-1].split(".")[0]] = pd.read_csv(pd.io.common.BytesIO(file_bytes))

    def features_processing(self):
        """
        Process the features of the training and testing data.
        This method should include any necessary feature engineering steps.
        """
        X_train = self.dataframes["X_train"]
        X_test = self.dataframes["X_test"]
        self.y_train = self.dataframes["y_train"]
        self.y_test = self.dataframes["y_test"]

        for col in boolean_features:
            X_train[col] = X_train[col].map(mapping_bool)
            X_test[col] = X_test[col].map(mapping_bool)

        X_train, X_test = features_prep([X_train, X_test])
        X_train = X_train[ML_FEATURE_COLS]
        X_test = X_test[ML_FEATURE_COLS]

        self.X_train_encoded = preprocess_features(X_train, price_level_map, ML_FEATURE_COLS)
        self.X_test_encoded = preprocess_features(
            X_test, price_level_map, ML_FEATURE_COLS, fit_columns=self.X_train_encoded.columns
        )

        print(
            "Total high energy Train",
            self.y_train[self.y_train].shape,
            self.y_train[self.y_train].shape[0] / X_train.shape[0] * 100,
        )
        print(
            "Total high energy test",
            self.y_test[self.y_test].shape,
            self.y_test[self.y_test].shape[0] / X_test.shape[0] * 100,
        )

        print(
            "Total non high energy Train",
            self.y_train[~self.y_train].shape,
            self.y_train[~self.y_train].shape[0] / X_train.shape[0] * 100,
        )
        print(
            "Total non high energy test",
            self.y_test[~self.y_test].shape,
            self.y_test[~self.y_test].shape[0] / X_test.shape[0] * 100,
        )

    def training_model(self):
        """
        Train the model using the processed features.
        This method should include the model training logic.
        """
        _, self.trained_models, _ = ml_experiment(
            X_train=self.X_train_encoded.fillna(0),
            y_train=self.y_train,
            X_test=self.X_test_encoded.fillna(0),
            y_test=self.y_test,
        )

    def save_model(self):
        """
        Save the trained model to a file.
        This method properly serializes and uploads the model to GCS.
        """

        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as tmp_file:
            temp_dir = os.path.dirname(tmp_file.name)
        temp_path = os.path.join(temp_dir, "model.pkl")
        # Save model to the specific file name
        joblib.dump(self.trained_models["CatBoost"], temp_path)

        try:
            # Upload the file
            self.uploader.upload_files(file_paths=temp_path, destination_prefix=f"{MODEL_FOLDER_NAME}/")
            print(f"Model saved successfully.")
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
