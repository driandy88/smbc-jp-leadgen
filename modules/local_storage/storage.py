"""
Local-disk stand-ins for GCSUploader / GCSDownloader. Paths are relative to `root_dir`,
mirroring the GCS object layout so pipelines can switch storage without other changes.
"""

from pathlib import Path
from typing import Dict, List

import pandas as pd


class LocalUploader:
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def upload_dataframe(self, df: pd.DataFrame, gcs_path: str, file_format: str = "csv", **format_kwargs) -> Dict:
        local_path = self.root_dir / gcs_path
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if file_format.lower() == "csv":
                df.to_csv(local_path, index=False, **format_kwargs)
            elif file_format.lower() == "json":
                df.to_json(local_path, orient="records", **format_kwargs)
            elif file_format.lower() == "parquet":
                df.to_parquet(local_path, index=False, **format_kwargs)
            else:
                raise ValueError(f"Unsupported format: {file_format}")
            return {"successful": [{"local_path": "DataFrame", "gcs_path": str(local_path)}], "failed": [], "total": 1}
        except Exception as e:
            return {
                "successful": [],
                "failed": [{"local_path": "DataFrame", "gcs_path": str(local_path), "error": f"✗ Failed: {e}"}],
                "total": 1,
            }


class LocalDownloader:
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)

    def download_csv_files(self, gcs_paths: List[str]) -> Dict[str, bytes]:
        csv_bytes = {}
        for gcs_path in gcs_paths:
            local_path = self.root_dir / gcs_path
            if local_path.is_file():
                csv_bytes[gcs_path] = local_path.read_bytes()
            else:
                print(f"File not found: {local_path}")
        return csv_bytes

    def download_csv(self, gcs_path: str):
        return self.download_csv_files([gcs_path]).get(gcs_path)

    def get_folder_list(self, prefix: str) -> List[str]:
        """Immediate sub-folders of `prefix`, as 'prefix/sub/' strings, newest name first."""
        base = self.root_dir / prefix
        if not base.is_dir():
            return []
        return sorted((f"{prefix.rstrip('/')}/{p.name}/" for p in base.iterdir() if p.is_dir()), reverse=True)

    def get_file_list(self, prefix: str) -> List[str]:
        base = self.root_dir / prefix
        if not base.is_dir():
            return []
        return sorted(str(p.relative_to(self.root_dir)) for p in base.rglob("*") if p.is_file())
