import asyncio

from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

from app.core.events import bus
from app.core.responses import dumps

router = APIRouter(tags=["System"])

HEARTBEAT_S = 20


@router.get("/stream", summary="Live event stream (Server-Sent Events)")
async def stream(request: Request):
    """SSE stream of pipeline, ingestion, analysis and alert events. Clients refresh the
    affected data when an event arrives. A heartbeat is sent every 20 s."""
    queue = bus.subscribe()

    async def events():
        try:
            yield f"event: hello\ndata: {dumps({'subscribers': bus.subscriber_count})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
                    yield f"event: {message['type']}\ndata: {dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
