"""Runtime configuration, read once from the environment (and .env locally)."""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: _env("APP_ENV", "local"))
    secret_key: str = field(default_factory=lambda: _env("APP_SECRET_KEY", "local-dev-secret"))

    # Single hardcoded account and the billing passcode (requested as manual/hardcoded for now)
    login_email: str = field(default_factory=lambda: _env("LOGIN_EMAIL", "daniel.riandy@artefact.com"))
    login_password: str = field(default_factory=lambda: _env("LOGIN_PASSWORD", "test12345"))
    billing_passcode: str = field(default_factory=lambda: _env("BILLING_PASSCODE", "test12345"))

    # Postgres on Cloud Run (unix socket via /cloudsql), SQLite file locally
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    db_user: str = field(default_factory=lambda: _env("DB_USER", "hexline"))
    db_password: str = field(default_factory=lambda: _env("DB_PASSWORD"))
    db_name: str = field(default_factory=lambda: _env("DB_NAME", "hexline"))
    cloudsql_instance: str = field(default_factory=lambda: _env("CLOUDSQL_INSTANCE"))

    gcp_project: str = field(default_factory=lambda: _env("GCP_PROJECT_ID", "smbc-leadgen-1833"))
    gcp_region: str = field(default_factory=lambda: _env("GCP_REGION", "asia-northeast1"))
    # Empty bucket keeps raw CSVs on local disk under output/
    gcs_bucket: str = field(default_factory=lambda: _env("GCS_BUCKET"))
    local_output_dir: str = field(default_factory=lambda: _env("LOCAL_OUTPUT_DIR", str(REPO_ROOT / "output")))

    maps_api_key: str = field(default_factory=lambda: _env("GOOGLE_MAPS_API_KEY"))
    # "*" bills every Text Search call at the Enterprise + Atmosphere SKU
    places_field_mask: str = field(default_factory=lambda: _env("PLACES_FIELD_MASK", "*"))
    places_usd_per_1000: float = field(default_factory=lambda: float(_env("PLACES_USD_PER_1000", "40")))
    # Display currency for all costs (Google and Vertex bill in USD)
    currency: str = field(default_factory=lambda: _env("CURRENCY", "SGD"))
    usd_rate: float = field(default_factory=lambda: float(_env("USD_RATE", "1.30")))
    monthly_budget: float = field(default_factory=lambda: float(_env("MONTHLY_BUDGET", "1300")))

    vertex_region: str = field(default_factory=lambda: _env("VERTEX_REGION", "global"))
    claude_model: str = field(default_factory=lambda: _env("CLAUDE_MODEL", "claude-sonnet-5-5"))
    # Sonnet 5.5 on Vertex, per 1M tokens
    claude_usd_per_mtok_in: float = field(default_factory=lambda: float(_env("CLAUDE_USD_PER_MTOK_IN", "2")))
    claude_usd_per_mtok_out: float = field(default_factory=lambda: float(_env("CLAUDE_USD_PER_MTOK_OUT", "10")))

    # "thread" runs collection inside the API process; "job" starts a Cloud Run Job execution
    execution_mode: str = field(default_factory=lambda: _env("EXECUTION_MODE", "thread"))
    collect_job_name: str = field(default_factory=lambda: _env("COLLECT_JOB_NAME", "hexline-collect"))
    # Parallel searches per run, and a cap on Places calls per second across them (quota is 600/min)
    collect_workers: int = field(default_factory=lambda: int(_env("COLLECT_WORKERS", "8")))
    places_qps: float = field(default_factory=lambda: float(_env("PLACES_QPS", "8")))
    # Default for the Real API / Mock toggle in the UI
    default_mock: bool = field(default_factory=lambda: _env("DEFAULT_MOCK", "true").lower() == "true")

    frontend_dist: str = field(default_factory=lambda: _env("FRONTEND_DIST", str(REPO_ROOT / "frontend" / "dist")))

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.cloudsql_instance:
            return (
                f"postgresql+psycopg://{self.db_user}:{self.db_password}@/{self.db_name}"
                f"?host=/cloudsql/{self.cloudsql_instance}"
            )
        return f"sqlite:///{REPO_ROOT / 'hexline.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
