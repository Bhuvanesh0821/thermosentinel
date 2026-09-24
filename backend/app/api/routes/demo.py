"""Test-fixture demonstration endpoints (DATA_MODE=test-fixture on a *_test database only)."""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin, require_db
from app.api.schemas import ERROR_RESPONSES
from app.core.errors import NotFoundError
from app.core.responses import ok
from app.config import get_settings
from app.db.locks import job_lease

router = APIRouter(tags=["Test fixture (development only)"], responses=ERROR_RESPONSES)


def _require_test_mode() -> None:
    # Invisible (404) in live mode, so production never exposes these operations.
    if not get_settings().test_fixture_mode:
        raise NotFoundError("Not found")


@router.post("/demo/replay", dependencies=[Depends(_require_test_mode), Depends(require_db), Depends(require_admin)],
             summary="Replay the labelled FIRMS test fixture")
def post_replay():
    """Replays the recorded FIRMS sample (source_mode='test_fixture') and runs analysis, so an
    alert is generated and streamed exactly like a live one. Test databases only."""
    from app.demo.fixture import replay

    with job_lease("pipeline"):
        return ok(replay())


@router.post("/demo/reset", dependencies=[Depends(_require_test_mode), Depends(require_db), Depends(require_admin)],
             summary="Remove replayed test-fixture data")
def post_reset():
    from app.demo.fixture import reset

    with job_lease("pipeline"):
        return ok(reset())
