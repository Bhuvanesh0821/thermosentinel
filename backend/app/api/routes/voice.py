from typing import Literal

from fastapi import APIRouter, Body, Depends, Query

from app.api.deps import require_db
from app.api.schemas import ERROR_RESPONSES
from app.core.responses import ok
from app.db.engine import connection
from app.voice.briefing import build_briefing
from app.voice import lexicon
from app.voice.interpreter import interpret

router = APIRouter(tags=["Voice"], dependencies=[Depends(require_db)], responses=ERROR_RESPONSES)


@router.get("/voice/briefing", summary="Spoken situation briefing (text)")
def get_briefing(hours: int = Query(24, ge=1, le=168)):
    """Plain-language briefing built from live data, for text-to-speech in the client.
    The underlying facts are returned in `data.facts`."""
    with connection() as conn:
        return ok(build_briefing(conn, hours))


@router.post("/voice/interpret", summary="Interpret a voice / typed command")
def post_interpret(
    text: str = Body(..., min_length=1, max_length=300),
    lang: Literal["en", "hi", "ta"] | None = Body(None, description="Reply language; detected from the script when omitted"),
):
    """Understands free-form requests in English, Hindi or Tamil (including romanised mixes) and maps
    them to one whitelisted UI action (open a page, filter, focus the map, change the basemap) or a
    data-backed answer in the same language. Unsupported requests return `supported: false` with
    suggestions - nothing is executed."""
    with connection() as conn:
        result = interpret(text, conn, lang)
    return ok(result.as_dict(), {"transcript": text})


@router.get("/voice/commands", summary="Supported voice commands")
def get_commands(lang: Literal["en", "hi", "ta"] = "en"):
    return ok(lexicon.EXAMPLES[lang])
