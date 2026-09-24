from fastapi import APIRouter, Depends

from app.api.deps import require_db
from app.api.schemas import ERROR_RESPONSES
from app.core.errors import NotFoundError
from app.core.responses import ok
from app.db.engine import connection
from app.investigation.service import investigation

router = APIRouter(tags=["Incidents"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)


@router.get("/investigations/{incident_id}", summary="Incident investigation workspace")
def get_investigation(incident_id: int):
    """Complete evidence trail for one incident: timeline, detections (FRP, satellite, confidence),
    per-day and per-satellite summaries, cluster, facility relationship and outline, persistence,
    classification rationale, intelligence factors, alert history and data provenance."""
    with connection() as conn:
        data = investigation(conn, incident_id)
    if not data:
        raise NotFoundError(f"Incident {incident_id} not found")
    return ok(data)
