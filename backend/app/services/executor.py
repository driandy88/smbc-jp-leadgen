"""Start a collection run: in a background thread (local) or as a Cloud Run Job execution (prod).

Cloud Run throttles CPU outside requests, so long runs on the service itself would stall; the
job runs the same Collector with `python -m app.jobs collect --run-id N`.
"""

import logging
import threading

from app.services.collector import Collector
from app.settings import get_settings

logger = logging.getLogger(__name__)


def start(run_id: int) -> str:
    s = get_settings()
    if s.execution_mode == "job":
        from google.cloud import run_v2

        client = run_v2.JobsClient()
        name = client.job_path(s.gcp_project, s.gcp_region, s.collect_job_name)
        request = run_v2.RunJobRequest(
            name=name,
            overrides=run_v2.RunJobRequest.Overrides(
                container_overrides=[run_v2.RunJobRequest.Overrides.ContainerOverride(
                    args=["-m", "app.jobs", "collect", "--run-id", str(run_id)])]
            ),
        )
        op = client.run_job(request=request)
        logger.info("started job execution for run %s: %s", run_id, op.metadata.name if op.metadata else "")
        return "job"

    threading.Thread(target=Collector(run_id).run, name=f"collect-{run_id}", daemon=True).start()
    return "thread"
