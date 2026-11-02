import numpy as np
import pandas as pd
from sklearn.utils import shuffle

from config.gcs import ASPIRE_DATASET_FOLDER_NAME, TRAINING_DATASET_FOLDER_NAME, UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME
from config.models import FEATURES_NEEDED_FOR_TRAINING
from modules.google_cloud_storage.downloader import GCSDownloader
from modules.google_cloud_storage.uploader import GCSUploader


class TrainTestSplit:
    def __init__(self):
        self.downloader = GCSDownloader()
        self.uploader = GCSUploader()

    def load_aspire_training_data(self):
        gcs_path = f"{TRAINING_DATASET_FOLDER_NAME}/training_data.csv"
        file_bytes = self.downloader.download_csv(gcs_path)
        self.training_data = pd.read_csv(pd.io.common.BytesIO(file_bytes))
        self.training_data = self.training_data[self.training_data["id"].notna()]
        self.training_data["source"] = "aspire"
        print(f"Data loaded from {gcs_path}. Shape: {self.training_data.shape}")

    def load_manual_review_training_data(self):
        gcs_path = f"{UNIVERSE_DISCOVERY_RESULT_FOLDER_NAME}/data-extraction.csv"
        file_bytes = self.downloader.download_csv(gcs_path)
        google_maps_all_data = pd.read_csv(pd.io.common.BytesIO(file_bytes))

        gcs_path = f"{ASPIRE_DATASET_FOLDER_NAME}/ManualReviewMasterData.xlsx - List of Doors.csv"
        file_bytes = self.downloader.download_csv(gcs_path)
        manual_review = pd.read_csv(pd.io.common.BytesIO(file_bytes))
        manual_review = manual_review[manual_review.x == 1]
        manual_review = manual_review[["googleMapsUri", "Pierre HE Manual Review "]].merge(
            google_maps_all_data[FEATURES_NEEDED_FOR_TRAINING], on="googleMapsUri", how="left"
        )

        manual_review.rename(columns={"Pierre HE Manual Review ": "is_high_energy"}, inplace=True)
        manual_review["source"] = "manual_review"

        self.manual_review = manual_review

    def create_train_test_split(self):
        X_train, X_test, y_train, y_test = self._custom_train_test_split(df=self.training_data)

        X_train_mr, X_test_mr, y_train_mr, y_test_mr = self._custom_train_test_split(df=self.manual_review)

        self.X_train = pd.concat([X_train, X_train_mr], axis=0).reset_index(drop=True)
        self.y_train = pd.concat([y_train, y_train_mr], axis=0).reset_index(drop=True)
        self.X_test = pd.concat([X_test, X_test_mr], axis=0).reset_index(drop=True)
        self.y_test = pd.concat([y_test, y_test_mr], axis=0).reset_index(drop=True)

    def save_train_test_split(self):
        for data in [self.X_train, self.y_train, self.X_test, self.y_test]:
            var_name = [k for k, v in self.__dict__.items() if v is data][0]
            print(var_name)
            self.uploader.upload_dataframe(df=data, gcs_path=f"{TRAINING_DATASET_FOLDER_NAME}/{var_name}.csv")

    def run(self):
        self.load_aspire_training_data()
        self.load_manual_review_training_data()

        self.training_data = pd.concat([self.training_data, self.manual_review], axis=0).reset_index(drop=True)

        self.create_train_test_split()
        self.save_train_test_split()

    def _custom_train_test_split(
        self, df, target_col="is_high_energy", test_size=0.2, test_high_energy_ratio=0.03, random_state=42
    ):
        """
        Custom train-test split with specific target distribution in test set.

        Parameters:
        -----------
        df : pandas.DataFrame
            Input dataframe containing features and target
        target_col : str, default='is_high_energy'
            Name of the target column
        test_size : float, default=0.2
            Proportion of dataset to include in test split (0.2 = 20%)
        test_high_energy_ratio : float, default=0.03
            Ratio of high energy samples in test set (0.03 = 3%)
        random_state : int, default=42
            Random state for reproducible results

        Returns:
        --------
        X_train, X_test, y_train, y_test : pandas.DataFrame, pandas.DataFrame, pandas.Series, pandas.Series
            Train and test splits for features (X) and target (y)
        """

        # Set random seed for reproducibility
        np.random.seed(random_state)

        # Separate features and target
        X = df.drop(columns=[target_col])
        y = df[target_col]

        # Calculate test set size
        total_samples = len(df)
        test_samples = int(total_samples * test_size)

        # Calculate required samples for each class in test set
        test_high_energy_samples = int(test_samples * test_high_energy_ratio)
        test_low_energy_samples = test_samples - test_high_energy_samples

        print(f"Debug: Calculated test_samples = {test_samples}")
        print(f"Debug: test_high_energy_samples = {test_high_energy_samples}")
        print(f"Debug: test_low_energy_samples = {test_low_energy_samples}")

        # Separate data by target class
        high_energy_mask = y == 1
        low_energy_mask = y == 0

        high_energy_indices = df[high_energy_mask].index
        low_energy_indices = df[low_energy_mask].index

        # Check if we have enough samples of each class
        print(f"Debug: Available high energy samples: {len(high_energy_indices)}")
        print(f"Debug: Available low energy samples: {len(low_energy_indices)}")

        if len(high_energy_indices) < test_high_energy_samples:
            print(
                f"Warning: Not enough high energy samples. Required: {test_high_energy_samples}, Available: {len(high_energy_indices)}"
            )
            test_high_energy_samples = len(high_energy_indices)
            test_low_energy_samples = test_samples - test_high_energy_samples

        if len(low_energy_indices) < test_low_energy_samples:
            print(
                f"Warning: Not enough low energy samples. Required: {test_low_energy_samples}, Available: {len(low_energy_indices)}"
            )
            test_low_energy_samples = len(low_energy_indices)
            test_high_energy_samples = test_samples - test_low_energy_samples

        print(f"Debug: Final test_high_energy_samples = {test_high_energy_samples}")
        print(f"Debug: Final test_low_energy_samples = {test_low_energy_samples}")

        # Randomly sample indices for test set
        test_high_energy_idx = np.random.choice(high_energy_indices, size=test_high_energy_samples, replace=False)
        test_low_energy_idx = np.random.choice(low_energy_indices, size=test_low_energy_samples, replace=False)

        # Combine test indices
        test_indices = np.concatenate([test_high_energy_idx, test_low_energy_idx])

        # Get training indices (all remaining indices)
        train_indices = df.index[~df.index.isin(test_indices)]

        # Create train and test sets
        X_train = X.loc[train_indices].reset_index(drop=True)
        X_test = X.loc[test_indices].reset_index(drop=True)
        y_train = y.loc[train_indices].reset_index(drop=True)
        y_test = y.loc[test_indices].reset_index(drop=True)

        # Shuffle test set to mix high and low energy samples
        X_test, y_test = shuffle(X_test, y_test, random_state=random_state)

        # Print summary statistics
        print("Dataset Split Summary:")
        print(f"Total samples: {total_samples}")
        print(f"Training samples: {len(X_train)} ({len(X_train) / total_samples:.1%})")
        print(f"Test samples: {len(X_test)} ({len(X_test) / total_samples:.1%})")
        print()
        print("Training set distribution:")
        print(f"  High energy: {y_train.sum()} ({y_train.mean():.1%})")
        print(f"  Low energy: {len(y_train) - y_train.sum()} ({1 - y_train.mean():.1%})")
        print()
        print("Test set distribution:")
        print(f"  High energy: {y_test.sum()} ({y_test.mean():.1%})")
        print(f"  Low energy: {len(y_test) - y_test.sum()} ({1 - y_test.mean():.1%})")

        return X_train, X_test, y_train, y_test
