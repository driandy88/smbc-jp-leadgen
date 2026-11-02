import logging
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional

from google.cloud import storage

from config.gcs import BUCKET_NAME, PROJECT_ID


@dataclass
class ShapefileComponents:
    country_code: str
    files: Dict[str, bytes]
    total_size_mb: float


logger = logging.getLogger(__name__)


class GCSDownloader:
    def __init__(self, bucket_name: str = BUCKET_NAME, env: str = "dev"):
        self.client = storage.Client(project=PROJECT_ID + "-" + env)
        self.bucket_name = bucket_name
        self.bucket = self.client.bucket(bucket_name)
        if not self.bucket.exists():
            raise ValueError(f"Bucket '{bucket_name}' does not exist")

    def download_csv_files(self, gcs_paths: List[str]) -> Dict[str, bytes]:
        """
        Download CSV files from GCS and return their content as bytes.

        Args:
            gcs_paths: List of GCS file paths (relative to the bucket root).

        Returns:
            Dictionary mapping file paths to bytes content.
        """
        csv_bytes = {}

        def download_csv(gcs_path):
            try:
                blob = self.bucket.blob(gcs_path)
                if blob.exists():
                    content = blob.download_as_bytes()
                    print(f"Downloaded {gcs_path}: {len(content):,} bytes")
                    return gcs_path, content
                else:
                    print(f"File not found: {gcs_path}")
                    return gcs_path, None
            except Exception as e:
                print(f"Error downloading {gcs_path}: {e}")
                return gcs_path, None

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(download_csv, path) for path in gcs_paths]
            for future in as_completed(futures):
                gcs_path, content = future.result()
                if content:
                    csv_bytes[gcs_path] = content

        return csv_bytes

    def download_to_memory(self, gcs_path: str) -> Optional[Dict[str, bytes]]:
        """
        STEP 1: Download shapefile components to memory as bytes

        Args:
            country_code: Country code (e.g., 'vnm', 'usa')

        Returns:
            Dictionary mapping file extensions to bytes content
            e.g., {'.shp': b'...', '.shx': b'...', '.dbf': b'...'}
        """
        print(f"STEP 1: Downloading {gcs_path} to memory...")

        extensions = [".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj"]

        def download_component(ext):
            """Download single component to memory"""
            try:
                file_path = f"{gcs_path}{ext}"
                blob = self.bucket.blob(file_path)

                if blob.exists():
                    content = blob.download_as_bytes()
                    return ext, content
                return ext, None
            except Exception as e:
                print(f"Error downloading {ext}: {e}")
                return ext, None

        shapefile_bytes = {}

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(download_component, ext) for ext in extensions]

            for future in as_completed(futures):
                ext, content = future.result()
                if content:
                    shapefile_bytes[ext] = content
                    print(f"  Downloaded {gcs_path}{ext}: {len(content):,} bytes")

        # Check if we have required files
        required = {".shp", ".shx", ".dbf"}
        if not required.issubset(set(shapefile_bytes.keys())):
            missing = required - set(shapefile_bytes.keys())
            print(f"Missing required files: {missing}")
            return None

        total_size = sum(len(content) for content in shapefile_bytes.values())
        print(f"✓ Downloaded {gcs_path} to memory: {total_size:,} bytes total")

        return shapefile_bytes

    def save_to_temp_files(self, shapefile_bytes: Dict[str, bytes], country_code: str) -> Optional[str]:
        """
        STEP 2: Save bytes content to temporary files

        Args:
            shapefile_bytes: Dictionary from step1_download_to_memory()
                            Format: {'.shp': b'...', '.shx': b'...', '.dbf': b'...'}
            country_code: Country code for naming files

        Returns:
            Path to the .shp file, or None if failed
        """
        print(f"STEP 2: Saving {country_code} bytes to temporary files...")

        # Validate input
        if not isinstance(shapefile_bytes, dict):
            print(f"Error: shapefile_bytes must be a dictionary, got {type(shapefile_bytes)}")
            return None

        if not shapefile_bytes:
            print(f"Error: shapefile_bytes is empty")
            return None

        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix=f"shapefile_{country_code}_")

        try:
            # Save each component to a file
            shp_file_path = None
            saved_files = []

            for ext, content in shapefile_bytes.items():
                if not isinstance(content, bytes):
                    print(f"Warning: {ext} content is not bytes, got {type(content)}")
                    continue

                file_path = os.path.join(temp_dir, f"{country_code}{ext}")

                with open(file_path, "wb") as f:
                    f.write(content)

                saved_files.append(f"{country_code}{ext}")
                print(f"  Saved {country_code}{ext}: {len(content):,} bytes -> {file_path}")

                # Remember the .shp file path
                if ext == ".shp":
                    shp_file_path = file_path

            if not shp_file_path:
                print(f"Error: No .shp file found in shapefile_bytes")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            print(f"✓ Saved {country_code} to temp directory: {temp_dir}")
            print(f"  Files saved: {saved_files}")
            return shp_file_path

        except Exception as e:
            print(f"Error saving to temp files: {e}")
            print(f"shapefile_bytes type: {type(shapefile_bytes)}")
            print(
                f"shapefile_bytes keys: {list(shapefile_bytes.keys()) if hasattr(shapefile_bytes, 'keys') else 'No keys method'}"
            )
            # Clean up on error
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

    def get_folder_list(self, prefix):
        blobs = self.bucket.list_blobs(prefix=prefix, delimiter="/")

        folders = set()
        for page in blobs.pages:
            for folder in page.prefixes:
                folders.add(folder)

        return list(sorted(folders, reverse=True))

    def get_file_list(self, prefix):
        return [file.name for file in self.bucket.list_blobs(prefix=prefix)]

    def download_csv(self, gcs_path):
        try:
            blob = self.bucket.blob(gcs_path)
            if blob.exists():
                content = blob.download_as_bytes()
                print(f"Downloaded {gcs_path}: {len(content):,} bytes")
                return content
            else:
                print(f"File not found: {gcs_path}")
                return None
        except Exception as e:
            print(f"Error downloading {gcs_path}: {e}")
            return None

