from fastapi import APIRouter, Depends, Query

from app.api.deps import parse_csv_list, require_db
from app.api.schemas import ERROR_RESPONSES
from app.core.responses import ok
from app.db.engine import connection
from app.search.service import search

router = APIRouter(tags=["Search"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)

TYPES = {"facilities", "incidents", "alerts", "locations"}


@router.get("/search", summary="Search facilities, incidents, alerts and locations")
def get_search(
    q: str = Query(..., min_length=2, max_length=120),
    types: str | None = Query(None, description="Comma-separated subset of: facilities, incidents, alerts, locations"),
    limit: int = Query(6, ge=1, le=25),
):
    """Facilities (name/operator), incidents (title or INC-reference), alerts (title/description) and
    locations (coordinates or OpenStreetMap Nominatim, clipped to India's monitoring area)."""
    wanted = set(parse_csv_list(types, TYPES, "type") or TYPES)
    with connection() as conn:
        results = search(conn, q, wanted, limit)
    return ok(results, {"q": q, "count": sum(len(v) for v in results.values())})
