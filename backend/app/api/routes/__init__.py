from fastapi import APIRouter

from app.api.routes import (
    alerts,
    analytics,
    clusters,
    data_sources,
    demo,
    facilities,
    firms,
    health,
    hotspots,
    incidents,
    investigation,
    landcover,
    map_config,
    notifications,
    pipeline,
    search,
    stats,
    stream,
    system,
    voice,
)

api_router = APIRouter(prefix="/api")
for module in (
    health,
    system,
    firms,
    hotspots,
    facilities,
    clusters,
    incidents,
    investigation,
    alerts,
    notifications,
    data_sources,
    landcover,
    map_config,
    stats,
    analytics,
    search,
    stream,
    pipeline,
    voice,
    demo,
):
    api_router.include_router(module.router)
