import ast
import json
import os

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder

from config.models import boolean_features

price_level_map = {
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


def extract_hours(hours_json):
    """
    Extract typical opening and closing hours from JSON string

    Args:
        hours_json: JSON string with opening hours data

    Returns:
        tuple: (opening_hour, closing_hour) as integers (0-23)
               Returns (None, None) if parsing fails
    """
    if not hours_json or hours_json == "nan" or str(hours_json) == "nan":
        return None, None

    try:
        # Handle string input
        if isinstance(hours_json, str):
            hours_json = hours_json.strip()

            # Remove array wrapper if present
            if hours_json.startswith("['") and hours_json.endswith("']"):
                hours_json = hours_json[2:-2]

            # Try JSON first (double quotes)
            if hours_json.startswith("[") and '"' in hours_json:
                data = json.loads(hours_json)
            # Try Python literal eval (single quotes)
            elif hours_json.startswith("["):
                data = ast.literal_eval(hours_json)
            else:
                return None, None
        else:
            data = hours_json

        if not isinstance(data, list) or not data:
            return None, None

        # Extract hours
        open_times = []
        close_times = []

        for period in data:
            if isinstance(period, dict) and "open" in period and "close" in period:
                open_hour = period["open"].get("hour")
                close_hour = period["close"].get("hour")

                if open_hour is not None and close_hour is not None:
                    open_times.append(open_hour)
                    close_times.append(close_hour)

        if open_times and close_times:
            typical_open = int(np.median(open_times))
            typical_close = int(np.median(close_times))
            return typical_open, typical_close

        return None, None

    except Exception as e:
        return None, None


def balance_with_smote(X, y, random_state=42):
    """
    Balance the classes in X, y using SMOTE.
    Returns the resampled X and y.
    """
    smote = SMOTE(random_state=random_state)
    X_resampled, y_resampled = smote.fit_resample(X, y)
    return X_resampled, y_resampled


def features_prep(list_of_dfs: list):
    currency_to_usd = {
        "IDR": 16500,  # Indonesian Rupiah
        "SGD": 1.35,  # Singapore Dollar
        "HKD": 7.8,  # Hong Kong Dollar
        "AUD": 1.5,  # Australian Dollar
        "USD": 1.0,  # US Dollar
        "KRW": 1370,  # South Korean Won
        "JPY": 155,  # Japanese Yen
        "TWD": 32,  # Taiwan Dollar
        "MYR": 4.7,  # Malaysian Ringgit
        "VND": 25500,  # Vietnamese Dong
        "THB": 36,  # Thai Baht,
        "PHP": 57.5,  # Philippine Peso
    }

    for df in list_of_dfs:
        df["priceRange_startPrice_usd"] = df.apply(
            lambda row: row["priceRange_startPrice.units"]
            / currency_to_usd.get(row["priceRange_startPrice.currencyCode"], 1)
            if pd.notnull(row["priceRange_startPrice.units"]) and pd.notnull(row["priceRange_startPrice.currencyCode"])
            else None,
            axis=1,
        )
        df["priceRange_endPrice_usd"] = df.apply(
            lambda row: row["priceRange_endPrice.units"]
            / currency_to_usd.get(row["priceRange_endPrice.currencyCode"], 1)
            if pd.notnull(row["priceRange_endPrice.units"]) and pd.notnull(row["priceRange_endPrice.currencyCode"])
            else None,
            axis=1,
        )
        df["open_hour"] = df["regularOpeningHours_periods"].apply(lambda x: extract_hours(x)[0])
        df["close_hour"] = df["regularOpeningHours_periods"].apply(lambda x: extract_hours(x)[1])
        # for cat in important_primary_cats:
        #     df[f'primaryType_{cat}'] = df['primaryType'] == cat
        df.drop(
            ["regularOpeningHours_periods", "priceRange_startPrice.currencyCode", "priceRange_endPrice.currencyCode"],
            axis=1,
            inplace=True,
        )

    return list_of_dfs


def split_train_test(df, test_size=0.2, random_state=42):
    """
    Split the DataFrame into training and testing sets.
    Returns the training and testing DataFrames.
    """
    X = df.drop("is_high_energy", axis=1)
    y = df["is_high_energy"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=True)

    return X_train, X_test, y_train, y_test


def preprocess_features(X, price_level_map, ML_FEATURE_COLS, fit_columns=None):
    X = X.copy()
    # Map priceLevel to ordinal values
    X["priceLevel"] = X["priceLevel"].map(price_level_map)
    X["priceLevel"] = X["priceLevel"].fillna(0)
    X[boolean_features] = X[boolean_features].fillna(0)
    X[boolean_features] = X[boolean_features].astype(int)
    # Find categorical columns (excluding priceLevel)

    cat_cols = [col for col in ML_FEATURE_COLS if X[col].dtype == "object" and col != "priceLevel"]
    # One-hot encode
    # Fit encoder if fit_columns is not provided (i.e., training)
    if fit_columns is None:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse=False, drop="first")
        X_cat = encoder.fit_transform(X[cat_cols])
        cat_feature_names = encoder.get_feature_names_out(cat_cols)
        X_encoded = pd.DataFrame(X_cat, columns=cat_feature_names, index=X.index)
        X_encoded = pd.concat([X.drop(columns=cat_cols), X_encoded], axis=1)
        # Save encoder for later use if needed
        preprocess_features.encoder = encoder
    else:
        # Use encoder from training
        encoder = getattr(preprocess_features, "encoder", None)
        if encoder is None:
            raise ValueError("Encoder not found. Fit on training data first.")
        X_cat = encoder.transform(X[cat_cols])
        cat_feature_names = encoder.get_feature_names_out(cat_cols)
        X_encoded = pd.DataFrame(X_cat, columns=cat_feature_names, index=X.index)
        X_encoded = pd.concat([X.drop(columns=cat_cols), X_encoded], axis=1)
    # If fit_columns is provided, align columns to match train set
    if fit_columns is not None:
        X_encoded = X_encoded.reindex(columns=fit_columns, fill_value=0)
    return X_encoded


def fill_missing_with_mode(df):
    """
    Fill missing values in each column with its mode value.
    """
    df_filled = df.copy()
    for col in df.columns:
        if df[col].isna().any():
            mode_val = df[col].mode(dropna=True)
            if not mode_val.empty:
                df_filled[col] = df[col].fillna(mode_val[0])

    # df_filled['open_hour'] = df_filled['open_hour'].fillna(df_filled['open_hour'].mode(dropna=True))
    # df_filled['close_hour'] = df_filled['close_hour'].fillna(df_filled['close_hour'].mode(dropna=True))
    return df_filled
