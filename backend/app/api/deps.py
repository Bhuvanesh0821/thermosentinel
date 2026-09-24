"""Shared API dependencies and parameter helpers."""

from __future__ import annotations

import hmac

from fastapi import Header

from app.config import get_settings
from app.core.errors import BadRequestError, DatabaseNotConfiguredError, ForbiddenError
from app.db.engine import db_configured
from app.geo.region import BBox


def require_db() -> None:
    if not db_configured():
        raise DatabaseNotConfiguredError()


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Guards state-changing pipeline endpoints.

    * ADMIN_API_TOKEN set  -> the X-Admin-Token header must match.
    * not set, development -> allowed (local prototype convenience).
    * not set, production  -> refused.
    """
    settings = get_settings()
    expected = settings.admin_token_value
    if expected:
        if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
            raise ForbiddenError("A valid X-Admin-Token header is required for this operation.")
        return
    if settings.is_production:
        raise ForbiddenError("ADMIN_API_TOKEN must be configured to use this endpoint in production.")


def parse_bbox(value: str | None) -> BBox | None:
    if not value:
        return None
    try:
        return BBox.parse(value)
    except ValueError as exc:
        raise BadRequestError(f"Invalid bbox: {exc}") from exc


def parse_csv_list(value: str | None, allowed: set[str] | None = None, name: str = "value") -> list[str] | None:
    if not value:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    if allowed is not None:
        unknown = sorted(set(items) - allowed)
        if unknown:
            raise BadRequestError(f"Unknown {name}: {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}")
    return items or None
