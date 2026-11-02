import os
import tempfile

# Isolated SQLite DB and output folder per test session; set before the app is imported
_tmp = tempfile.mkdtemp(prefix="hexline-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["LOCAL_OUTPUT_DIR"] = f"{_tmp}/output"
os.environ["GCS_BUCKET"] = ""
os.environ["EXECUTION_MODE"] = "thread"
os.environ["GOOGLE_MAPS_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "daniel.riandy@artefact.com", "password": "test12345"})
    return {"Authorization": "Bearer " + r.json()["token"]}
