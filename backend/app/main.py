"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.responses import RedirectResponse

from app import __version__
from app.api.routes import api_router
from app.api.routes.ws import router as ws_router
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.events import bus
from app.db.engine import db_configured, dispose_engine
from app.logging_config import configure_logging

log = logging.getLogger("thermosentinel")

DESCRIPTION = """
**ThermoSentinel** - geospatial industrial thermal intelligence.

Integrates NASA FIRMS satellite thermal detections, OpenStreetMap industrial infrastructure and
ESA WorldCover land cover to cluster, classify, monitor and prioritise industrial thermal events.

* All data is real and sourced from the providers listed at `/api/data-sources`.
* Responses use a consistent envelope: `{"status": "ok", "data": ..., "meta": {...}}`;
  errors: `{"status": "error", "error": {"code", "message", "details"}}`.
* Classifications are inferences from satellite and open geospatial data, not confirmed ground truth.
"""


class UnsafeDataModeError(RuntimeError):
    """Live and test-fixture data must never share a database."""


def _check_data_mode(settings) -> None:
    from app.demo.fixture import live_database_contains_fixtures, test_mode_problems

    if settings.test_fixture_mode:
        problems = [p for p in test_mode_problems(settings) if "fixture file" not in p]
        if problems:
            raise UnsafeDataModeError("Refusing test-fixture mode: " + "; ".join(problems))
        log.warning("TEST-FIXTURE MODE: replayed, labelled sample data - not live", extra={"database": settings.database_name})
    elif live_database_contains_fixtures():
        raise UnsafeDataModeError(
            "This database contains test-fixture detections; a live API must not use it. "
            "Point DATABASE_URL at the live database or set DATA_MODE=test-fixture on a *_test database."
        )


def _startup_database() -> None:
    """Apply migrations and register data sources (best effort; the API stays up if Neon is unreachable)."""
    from app.db.migrate import apply_migrations
    from app.geo.region_sync import sync_monitoring_region
    from app.jobs import ensure_data_source_registry

    settings = get_settings()
    try:
        if settings.auto_migrate:
            result = apply_migrations()
            if result["applied"]:
                log.info("migrations applied", extra={"applied": result["applied"]})
        ensure_data_source_registry()
        sync_monitoring_region()
        _check_data_mode(settings)
    except UnsafeDataModeError:
        raise
    except Exception as exc:
        log.error("database initialisation failed; API will report degraded health", extra={"error": str(exc)[:500]})
        raise


def _start_background_jobs(settings) -> None:
    if settings.test_fixture_mode:
        log.info("scheduler disabled in test-fixture mode (no live FIRMS ingestion into a test database)")
        return
    if settings.scheduler_enabled:
        from app.scheduler import start_scheduler

        start_scheduler(settings)


async def _retry_database(settings) -> None:
    """Keep retrying database initialisation (e.g. while a suspended Neon compute wakes or the
    network recovers); start the scheduler once it succeeds. The API serves health and
    503s for data endpoints meanwhile."""
    attempt = 0
    while True:
        attempt += 1
        await asyncio.sleep(settings.db_startup_retry_seconds)
        try:
            await asyncio.to_thread(_startup_database)
        except UnsafeDataModeError as exc:
            log.critical("unsafe data mode; background jobs not started", extra={"error": str(exc)})
            return
        except Exception:
            log.warning("database still unavailable; will retry", extra={"attempt": attempt})
            continue
        log.info("database ready after retry", extra={"attempt": attempt})
        _start_background_jobs(settings)
        return


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    problems = settings.production_problems()
    if problems:
        # Fail the deploy loudly rather than run a production API that is insecure or cannot work.
        for p in problems:
            log.critical("unsafe production configuration", extra={"problem": p})
        raise RuntimeError("Refusing to start in production: " + "; ".join(problems))

    bus.bind_loop(asyncio.get_running_loop())
    retry_task = None
    db_ready = False
    if db_configured():
        try:
            await asyncio.to_thread(_startup_database)
            db_ready = True
        except UnsafeDataModeError as exc:
            log.critical("unsafe data mode", extra={"error": str(exc)})
            raise
        except Exception:
            retry_task = asyncio.create_task(_retry_database(settings))
    else:
        log.warning("DATABASE_URL not set - running without a database; data endpoints return 503")

    if db_ready:
        _start_background_jobs(settings)
    elif settings.scheduler_enabled and db_configured():
        log.warning("scheduler deferred until the database is reachable")

    log.info(
        "ThermoSentinel API started",
        extra={"version": __version__, "env": settings.app_env, "firms_mode": settings.firms_mode, "db_ready": db_ready,
               "cors_origins": settings.cors_origin_list},
    )
    yield

    if retry_task:
        retry_task.cancel()
    from app.scheduler import shutdown_scheduler

    shutdown_scheduler()
    dispose_engine()
    log.info("ThermoSentinel API stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    app = FastAPI(
        title="ThermoSentinel API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Admin-Token"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(ws_router)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=()")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/api/docs")

    return app


app = create_app()
