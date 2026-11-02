import ast
import json
import re

import numpy as np
import pandas as pd


def fix_malformed_json(json_string):
    """
    Fix common JSON formatting issues
    """
    # Handle numpy arrays/pandas Series by converting to scalar
    if hasattr(json_string, "iloc") or isinstance(json_string, np.ndarray):
        # If it's a Series or array with one element, get the scalar value
        if hasattr(json_string, "iloc") and len(json_string) == 1:
            json_string = json_string.iloc[0]
        elif isinstance(json_string, np.ndarray) and json_string.size == 1:
            json_string = json_string.item()
        else:
            # If it's a multi-element array/series, return empty dict
            return {}

    # Handle lists that might be passed directly
    if isinstance(json_string, list):
        return json_string  # Return the list as-is for processing

    # Handle dictionaries that might be passed directly
    if isinstance(json_string, dict):
        return json_string  # Return the dict as-is

    # Now check for NaN values (only works on scalars)
    try:
        if pd.isna(json_string) or json_string == "NaN":
            return {}
    except (ValueError, TypeError):
        # If pd.isna fails, it's not a standard scalar
        return {}

    if not isinstance(json_string, str):
        # Try to convert to string if it's not already
        try:
            json_string = str(json_string)
        except Exception:
            return {}

    # Method 1: Try standard JSON parsing first
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        pass

    # Method 2: Try Python literal_eval (for Python dict syntax)
    try:
        return ast.literal_eval(json_string)
    except (ValueError, SyntaxError):
        pass

    # Method 3: Fix single quotes to double quotes
    try:
        # Replace single quotes with double quotes (careful with contractions)
        fixed = json_string.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Method 4: More sophisticated quote fixing
    try:
        # Handle cases where there are contractions or apostrophes
        fixed = re.sub(r"'([^']*)':", r'"\1":', json_string)  # Fix keys
        fixed = re.sub(r":\s*'([^']*)'", r': "\1"', fixed)  # Fix values
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Method 5: Extract key-value pairs manually
    try:
        # For simple cases like {'text': 'value'}
        if json_string.startswith("{") and json_string.endswith("}"):
            # Simple regex extraction
            matches = re.findall(r"'([^']+)':\s*'([^']*)'", json_string)
            if matches:
                return {key: value for key, value in matches}
    except Exception as e:
        pass

    # If all methods fail, return empty dict
    return {}


def normalize_json_data(parsed_data, col_name, max_items=None):
    """
    Normalize JSON data, handling both dictionaries and lists with consistent column structure
    """
    if isinstance(parsed_data, dict):
        # Standard dictionary - normalize directly
        return pd.json_normalize(parsed_data, sep=".")
    elif isinstance(parsed_data, list):
        # List of items - handle different cases
        if len(parsed_data) == 0:
            return pd.DataFrame()

        # Check what's in the list
        if all(isinstance(item, dict) for item in parsed_data):
            # List of dictionaries - normalize each and add index
            result = {}
            for i, item in enumerate(parsed_data):
                flattened = pd.json_normalize(item, sep=".")
                for col in flattened.columns:
                    result[f"item_{i}_{col}"] = flattened[col].iloc[0]
            return pd.DataFrame([result])
        elif all(isinstance(item, (str, int, float, bool)) for item in parsed_data):
            # List of primitive values - create columns for each index
            result = {}
            for i, item in enumerate(parsed_data):
                result[f"item_{i}"] = item
            return pd.DataFrame([result])
        else:
            # Mixed list - convert to string representation
            result = {}
            for i, item in enumerate(parsed_data):
                result[f"item_{i}"] = str(item)
            return pd.DataFrame([result])
    else:
        # Single value - create a simple column
        return pd.DataFrame({col_name: [parsed_data]})


def flatten_universe_column(df, specific_columns=None):
    """
    Flatten JSON columns with malformed JSON handling and list support
    """
    print("=== Flattening with Malformed JSON Fix (List Support) ===\n")

    # Detect JSON-like columns if not specified
    if specific_columns is None:
        json_columns = []
        for col in df.columns:
            sample = df[col].dropna().head(10)
            if any(isinstance(val, str) and val.strip().startswith(("{", "[")) for val in sample):
                json_columns.append(col)
            elif any(isinstance(val, (dict, list)) for val in sample):
                json_columns.append(col)
    else:
        json_columns = specific_columns

    print(f"Processing columns: {json_columns}")

    df_result = df.copy()
    success_count = 0

    for col in json_columns:
        if col not in df_result.columns:
            print(f"⚠️  Column '{col}' not found")
            continue

        print(f"\nProcessing column: {col}")

        try:
            # Apply the fix function to each value
            print("  - Parsing JSON strings...")
            parsed_data = df_result[col].apply(lambda x: fix_malformed_json(x))

            # Check how many were successfully parsed
            successful_parses = sum(1 for item in parsed_data if item != {})
            print(f"  - Successfully parsed: {successful_parses}/{len(parsed_data)} rows")

            # Analyze the types of parsed data
            types_found = {}
            for item in parsed_data:
                item_type = type(item).__name__
                if item_type not in types_found:
                    types_found[item_type] = 0
                types_found[item_type] += 1

            print(f"  - Data types found: {types_found}")

            # Normalize each row individually to handle mixed types
            normalized_rows = []
            all_columns = set()

            # First pass: collect all possible columns
            for idx, item in enumerate(parsed_data):
                try:
                    normalized = normalize_json_data(item, col)
                    if not normalized.empty:
                        all_columns.update(normalized.columns)
                except Exception as e:
                    continue

            # Second pass: normalize with consistent column structure
            for idx, item in enumerate(parsed_data):
                try:
                    normalized = normalize_json_data(item, col)
                    if not normalized.empty:
                        # Ensure all columns are present
                        for col_name in all_columns:
                            if col_name not in normalized.columns:
                                normalized[col_name] = np.nan

                        # Reorder columns consistently
                        normalized = normalized.reindex(columns=sorted(all_columns), fill_value=np.nan)
                        normalized.index = [df_result.index[idx]]
                        normalized_rows.append(normalized)
                except Exception as e:
                    print(f"    Warning: Failed to normalize row {idx}: {e}")
                    continue

            # Combine all normalized rows
            if normalized_rows:
                flattened = pd.concat(normalized_rows, axis=0, ignore_index=False, sort=False)
                # No need to call fillna since we're already using np.nan
            else:
                print(f"  ❌ No data to flatten")
                continue

            # Add column prefix
            flattened.columns = [f"{col}_{subcol}" for subcol in flattened.columns]

            # Reindex to match original DataFrame with NaN for missing values
            flattened = flattened.reindex(df_result.index, fill_value=np.nan)

            # Add to result DataFrame
            df_result = pd.concat([df_result, flattened], axis=1)

            print(f"  ✅ Created {len(flattened.columns)} new columns: {list(flattened.columns)}")

            # Drop original column
            df_result = df_result.drop(columns=[col])
            success_count += 1

        except Exception as e:
            print(f"  ❌ Error processing {col}: {str(e)}")
            import traceback

            traceback.print_exc()
            continue
    return df_result
