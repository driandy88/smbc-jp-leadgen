"""Raw and exported CSVs: GCS when GCS_BUCKET is set, otherwise the local output/ folder.

Paths mirror the pipeline's layout: google-data-extraction/<run>/raw/<city>/<hex>-<keyword>.csv
"""

import io
import shutil
from pathlib import Path

import pandas as pd

from app.settings import get_settings
from config.gcs import GOOGLE_DATA_EXTRACTION_FOLDER_NAME
from modules.local_storage.storage import LocalUploader


class Storage:
    def __init__(self):
        s = get_settings()
        self.bucket_name = s.gcs_bucket
        if self.bucket_name:
            from google.cloud import storage

            self._bucket = storage.Client(project=s.gcp_project).bucket(self.bucket_name)
        else:
            self._local = LocalUploader(root_dir=s.local_output_dir)

    def put_csv(self, path: str, df: pd.DataFrame) -> str:
        if self.bucket_name:
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            self._bucket.blob(path).upload_from_string(buf.getvalue(), content_type="text/csv")
            return f"gs://{self.bucket_name}/{path}"
        result = self._local.upload_dataframe(df, path, "csv")
        if result["failed"]:
            raise OSError(result["failed"][0]["error"])
        return result["successful"][0]["gcs_path"]

    def put_file(self, path: str, local_file: str, content_type: str = "text/csv") -> str:
        """Upload a file already on disk; streams, so large exports never sit in memory."""
        if self.bucket_name:
            self._bucket.blob(path).upload_from_filename(local_file, content_type=content_type)
            return f"gs://{self.bucket_name}/{path}"
        dest = Path(self._local.root_dir) / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_file, dest)
        return str(dest)


def run_prefix(run_id: int, created: str) -> str:
    return f"{GOOGLE_DATA_EXTRACTION_FOLDER_NAME}/run-{run_id:05d}_{created}"
