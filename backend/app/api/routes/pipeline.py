import logging
import threading

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_admin, require_db
from app.core.responses import ok
from app.db.locks import JobBusyError, pipeline_lock
from app.jobs import job_state, run_full_pipeline

log = logging.getLogger(__name__)

router = APIRouter(tags=["Pipeline"])


@router.get("/pipeline/status", summary="Pipeline state")
def get_status():
    return ok(job_state())


@router.post(
    "/pipeline/run",
    status_code=202,
    dependencies=[Depends(require_db), Depends(require_admin)],
    summary="Run the data pipeline now",
)
def run_pipeline(
    facilities: bool | None = Query(None, description="Force (true) or skip (false) the OSM facility refresh; default: when due"),
    firms: bool = True,
    analysis: bool = True,
    backfill_days: int | None = Query(None, ge=1, le=60, description="FIRMS history to fetch (API mode only)"),
):
    """Starts ingestion + analysis in the background and returns immediately. Progress is
    published on /api/stream and visible at /api/pipeline/status. Requires X-Admin-Token when
    ADMIN_API_TOKEN is configured."""
    if pipeline_lock.locked():
        raise JobBusyError("A pipeline run is already in progress.")

    def work():
        try:
            run_full_pipeline(
                include_facilities=facilities,
                include_firms=firms,
                include_analysis=analysis,
                backfill_days=backfill_days,
                trigger="api",
            )
        except JobBusyError:
            log.info("manual pipeline run skipped: busy")
        except Exception:
            log.exception("manual pipeline run failed")

    threading.Thread(target=work, name="pipeline-manual", daemon=True).start()
    return ok({"accepted": True}, status_code=202)
