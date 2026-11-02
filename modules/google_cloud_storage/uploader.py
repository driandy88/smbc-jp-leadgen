"""
GCS Upload utilities with parallel processing support Supports folders, individual files, and pandas DataFrames
"""

import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from google.cloud import storage

from config.gcs import BUCKET_NAME, PROJECT_ID

logger = logging.getLogger(__name__)


class GCSUploader:
    """Generic handler for parallel uploads to Google Cloud Storage"""

    def __init__(self, bucket_name: str = BUCKET_NAME, max_workers: int = 10, env: str = "dev"):
        """
        Initialize GCS uploader

        Args:
            bucket_name: Name of the GCS bucket
            max_workers: Number of parallel upload threads
        """
        self.client = storage.Client(project=f"{PROJECT_ID}-{env}")
        self.bucket = self.client.bucket(bucket_name)
        self.bucket_name = bucket_name
        self.max_workers = max_workers

        # Verify bucket exists
        if not self.bucket.exists():
            raise ValueError(f"Bucket '{bucket_name}' does not exist")

    def append_dataframe_to_gcs_csv(self, df, folder_name, file_name):
        """
        Append DataFrame to existing CSV in GCS

        Args:
            df: pandas DataFrame to append
            bucket_name: GCS bucket name
            gcs_path: Path to existing CSV in GCS
        """
        gcs_path = f"{folder_name}/{file_name}"

        client = storage.Client()
        bucket = client.bucket(self.bucket_name)
        blob = bucket.blob(gcs_path)

        try:
            # Download existing CSV
            existing_csv = blob.download_as_text()
            existing_df = pd.read_csv(io.StringIO(existing_csv))

            # Append new data
            combined_df = pd.concat([existing_df, df], ignore_index=True)

            # Upload combined data
            csv_buffer = io.StringIO()
            combined_df.to_csv(csv_buffer, index=False)
            csv_string = csv_buffer.getvalue()

            blob.upload_from_string(csv_string, content_type="text/csv")
            print(f"✓ Appended {len(df)} rows to gs://{self.bucket_name}/{gcs_path}")

        except Exception as e:
            if "404" in str(e):  # File doesn't exist, create new
                self.upload_dataframe(df, gcs_path, file_format="csv")
            else:
                print(f"✗ Failed to append: {e}")

    def upload_folder(
        self,
        local_folder: str,
        destination_prefix: str = "",
        file_patterns: Optional[List[str]] = None,
        skip_existing: bool = False,
        preserve_structure: bool = True,
    ) -> Dict:
        """
        Upload entire folder with all its contents

        Args:
            local_folder: Path to local folder
            destination_prefix: GCS folder prefix (e.g., 'data/processed')
            file_patterns: List of file patterns to include (e.g., ['*.csv', '*.json'])
            skip_existing: Skip files that already exist in GCS
            preserve_structure: Maintain folder structure in GCS

        Returns:
            Dict with upload results
        """
        folder_path = Path(local_folder)
        if not folder_path.exists():
            raise ValueError(f"Local folder '{local_folder}' does not exist")

        # Get files to upload
        if file_patterns:
            files_to_upload = []
            for pattern in file_patterns:
                files_to_upload.extend(folder_path.rglob(pattern))
        else:
            files_to_upload = [f for f in folder_path.rglob("*") if f.is_file()]

        # Create upload tasks
        upload_tasks = []
        for file_path in files_to_upload:
            if preserve_structure:
                relative_path = file_path.relative_to(folder_path)
                gcs_path = (
                    f"{destination_prefix.rstrip('/')}/{relative_path.as_posix()}"
                    if destination_prefix
                    else relative_path.as_posix()
                )
            else:
                gcs_path = (
                    f"{destination_prefix.rstrip('/')}/{file_path.name}" if destination_prefix else file_path.name
                )

            upload_tasks.append((str(file_path), gcs_path, "file"))

        return self._execute_parallel_upload(upload_tasks, skip_existing)

    def upload_files(
        self,
        file_paths: Union[str, List[str]],
        destination_prefix: str = "",
        custom_names: Optional[List[str]] = None,
        skip_existing: bool = False,
    ) -> Dict:
        """
        Upload specific files

        Args:
            file_paths: Single file path or list of file paths
            destination_prefix: GCS folder prefix
            custom_names: Custom names for files in GCS (same order as file_paths)
            skip_existing: Skip files that already exist in GCS

        Returns:
            Dict with upload results
        """
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        upload_tasks = []
        for i, file_path in enumerate(file_paths):
            local_path = Path(file_path)
            if not local_path.exists():
                logger.warning(f"File not found: {file_path}")
                continue

            # Use custom name or original filename
            if custom_names and i < len(custom_names):
                filename = custom_names[i]
            else:
                filename = local_path.name

            gcs_path = f"{destination_prefix.rstrip('/')}/{filename}" if destination_prefix else filename
            upload_tasks.append((str(file_path), gcs_path, "file"))

        return self._execute_parallel_upload(upload_tasks, skip_existing)

    def upload_dataframe(self, df: pd.DataFrame, gcs_path: str, file_format: str = "csv", **format_kwargs) -> Dict:
        """
        Upload pandas DataFrame directly to GCS

        Args:
            df: Pandas DataFrame to upload
            gcs_path: Full GCS path (e.g., 'data/processed/my_data.csv')
            file_format: Format to save ('csv', 'json', 'parquet', 'excel')
            **format_kwargs: Additional arguments for pandas save methods

        Returns:
            Dict with upload results
        """
        try:
            buffer = io.BytesIO()

            # Save DataFrame to buffer based on format
            if file_format.lower() == "csv":
                df.to_csv(buffer, index=False, **format_kwargs)
            elif file_format.lower() == "json":
                df.to_json(buffer, orient="records", **format_kwargs)
            elif file_format.lower() == "parquet":
                df.to_parquet(buffer, index=False, **format_kwargs)
            elif file_format.lower() == "excel":
                df.to_excel(buffer, index=False, **format_kwargs)
            else:
                raise ValueError(f"Unsupported format: {file_format}")

            # Upload buffer to GCS
            buffer.seek(0)
            blob = self.bucket.blob(gcs_path)
            blob.upload_from_file(buffer)

            return {
                "successful": [
                    {
                        "local_path": f"DataFrame",
                        "gcs_path": gcs_path,
                        "message": f"✓ DataFrame uploaded to gs://{self.bucket_name}/{gcs_path}",
                    }
                ],
                "failed": [],
                "total": 1,
            }

        except Exception as e:
            return {
                "successful": [],
                "failed": [
                    {
                        "local_path": f"DataFrame({df.shape[0]}x{df.shape[1]})",
                        "gcs_path": gcs_path,
                        "error": f"✗ Failed: {str(e)}",
                    }
                ],
                "total": 1,
            }

    def upload_data(self, data: Any, gcs_path: str, data_format: str = "json") -> Dict:
        """
        Upload any Python object as JSON or text

        Args:
            data: Any serializable Python object
            gcs_path: Full GCS path
            data_format: 'json' or 'text'

        Returns:
            Dict with upload results
        """
        try:
            if data_format.lower() == "json":
                content = json.dumps(data, indent=2, default=str)
                content_type = "application/json"
            else:
                content = str(data)
                content_type = "text/plain"

            blob = self.bucket.blob(gcs_path)
            blob.upload_from_string(content, content_type=content_type)

            return {
                "successful": [
                    {
                        "local_path": f"{type(data).__name__} object",
                        "gcs_path": gcs_path,
                        "message": f"✓ Data uploaded to gs://{self.bucket_name}/{gcs_path}",
                    }
                ],
                "failed": [],
                "total": 1,
            }

        except Exception as e:
            return {
                "successful": [],
                "failed": [
                    {
                        "local_path": f"{type(data).__name__} object",
                        "gcs_path": gcs_path,
                        "error": f"✗ Failed: {str(e)}",
                    }
                ],
                "total": 1,
            }

    def _upload_single_file(self, local_path: str, gcs_path: str, upload_type: str = "file") -> Tuple[str, bool, str]:
        """Upload a single file to GCS"""
        try:
            blob = self.bucket.blob(gcs_path)
            blob.upload_from_filename(local_path)
            return local_path, True, f"✓ Uploaded to gs://{self.bucket_name}/{gcs_path}"
        except Exception as e:
            return local_path, False, f"✗ Failed: {str(e)}"

    def _execute_parallel_upload(self, upload_tasks: List[Tuple[str, str, str]], skip_existing: bool = False) -> Dict:
        """Execute uploads in parallel"""
        results = {"successful": [], "failed": [], "skipped": [], "total": len(upload_tasks)}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Check existing files if skip_existing is True
            if skip_existing:
                filtered_tasks = []
                for local_path, gcs_path, upload_type in upload_tasks:
                    blob = self.bucket.blob(gcs_path)
                    if blob.exists():
                        results["skipped"].append(
                            {
                                "local_path": local_path,
                                "gcs_path": gcs_path,
                                "message": f"⊘ Skipped (exists): {gcs_path}",
                            }
                        )
                        logger.info(f"⊘ Skipped (exists): {gcs_path}")
                    else:
                        filtered_tasks.append((local_path, gcs_path, upload_type))
                upload_tasks = filtered_tasks

            # Submit all tasks
            future_to_task = {
                executor.submit(self._upload_single_file, local_path, gcs_path, upload_type): (local_path, gcs_path)
                for local_path, gcs_path, upload_type in upload_tasks
            }

            # Process completed tasks
            for future in as_completed(future_to_task):
                local_path, gcs_path = future_to_task[future]
                file_path, success, message = future.result()

                if success:
                    results["successful"].append({"local_path": file_path, "gcs_path": gcs_path, "message": message})
                else:
                    results["failed"].append({"local_path": file_path, "gcs_path": gcs_path, "error": message})

                logger.info(message)

        # Print summary
        self._print_summary(results)
        return results

    def _print_summary(self, results: Dict):
        """Print simple, formal terminal summary"""

        # ANSI color codes for terminal
        class Colors:
            GREEN = "\033[92m"
            RED = "\033[91m"
            YELLOW = "\033[93m"
            BLUE = "\033[94m"
            BOLD = "\033[1m"
            END = "\033[0m"

        # Calculate stats
        total = results["total"]
        successful = len(results["successful"])
        failed = len(results["failed"])
        skipped = len(results.get("skipped", []))

        print(f"\n{Colors.BOLD}UPLOAD SUMMARY{Colors.END}")
        print("=" * 50)
        print(f"Total files: {total}")
        print(f"Successful: {Colors.GREEN}{successful}{Colors.END}")
        print(f"Failed: {Colors.RED}{failed}{Colors.END}")
        if skipped > 0:
            print(f"Skipped: {Colors.YELLOW}{skipped}{Colors.END}")

        # List successful uploads
        if successful > 0:
            print(f"\n{Colors.BOLD}SUCCESSFULLY UPLOADED FILES:{Colors.END}")
            for i, item in enumerate(results["successful"], 1):
                file_name = (
                    Path(item["local_path"]).name if "DataFrame" not in item["local_path"] else item["local_path"]
                )
                print(f"{i:3d}. {file_name} -> gs://{self.bucket_name}/{item['gcs_path']}")

        # List failed uploads
        if failed > 0:
            print(f"\n{Colors.BOLD}{Colors.RED}FAILED UPLOADS:{Colors.END}")
            for i, item in enumerate(results["failed"], 1):
                file_name = (
                    Path(item["local_path"]).name if "DataFrame" not in item["local_path"] else item["local_path"]
                )
                error_msg = item["error"].replace("Failed: ", "").replace("✗ ", "")
                print(f"{i:3d}. {Colors.RED}{file_name}{Colors.END} - {error_msg}")

        # List skipped files
        if skipped > 0:
            print(f"\n{Colors.BOLD}{Colors.YELLOW}SKIPPED FILES (already exist):{Colors.END}")
            for i, item in enumerate(results["skipped"], 1):
                file_name = Path(item["local_path"]).name
                print(f"{i:3d}. {file_name}")

        print("=" * 50)
