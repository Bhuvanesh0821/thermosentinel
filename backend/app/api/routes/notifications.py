from fastapi import APIRouter, Depends, Query

from app.api.deps import require_db
from app.api.schemas import ERROR_RESPONSES, ApiResponse, Notification
from app.core.responses import ok
from app.db.engine import connection, transaction
from app.repositories import incidents as repo

router = APIRouter(tags=["Notifications"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)


@router.get("/notifications", response_model=ApiResponse[list[Notification]], summary="In-app notifications")
def get_notifications(unread_only: bool = False, limit: int = Query(30, ge=1, le=200)):
    with connection() as conn:
        rows, unread = repo.list_notifications(conn, unread_only=unread_only, limit=limit)
    return ok(rows, {"count": len(rows), "unread": unread})


@router.post("/notifications/{notification_id}/read", summary="Mark a notification read")
def mark_read(notification_id: int):
    with transaction() as conn:
        changed = repo.mark_notifications_read(conn, [notification_id])
    return ok({"updated": changed})


@router.post("/notifications/read-all", summary="Mark all notifications read")
def mark_all_read():
    with transaction() as conn:
        changed = repo.mark_notifications_read(conn, None)
    return ok({"updated": changed})
