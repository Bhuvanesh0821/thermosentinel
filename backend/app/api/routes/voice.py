from fastapi import APIRouter, Body, Depends, Query

from app.api.deps import require_db
from app.api.schemas import ERROR_RESPONSES
from app.core.responses import ok
from app.db.engine import connection
from app.voice.briefing import build_briefing
from app.voice.interpreter import EXAMPLES, interpret

router = APIRouter(tags=["Voice"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)


@router.get("/voice/briefing", summary="Spoken situation briefing (text)")
def get_briefing(hours: int = Query(24, ge=1, le=168)):
    """Plain-language briefing built from live data, for text-to-speech in the client.
    The underlying facts are returned in `data.facts`."""
    with connection() as conn:
        return ok(build_briefing(conn, hours))


@router.post("/voice/interpret", summary="Interpret a voice / typed command")
def post_interpret(text: str = Body(..., embed=True, min_length=1, max_length=300)):
    """Maps a transcript to one whitelisted action (navigate, focus the map, or answer from stored
    data). Unsupported commands return `supported: false` with suggestions - nothing is executed."""
    with connection() as conn:
        result = interpret(text, conn)
    return ok(result.as_dict(), {"transcript": text})


@router.get("/voice/commands", summary="Supported voice commands")
def get_commands():
    return ok(EXAMPLES)
