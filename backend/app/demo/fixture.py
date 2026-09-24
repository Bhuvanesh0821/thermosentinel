"""Test-fixture replay for demonstrations (DATA_MODE=test-fixture only).

Replays the recorded NASA FIRMS VIIRS sample (tests/fixtures/firms_viirs_snpp_sample.csv, real
rows captured from the public feed) into a SEPARATE database whose name ends in `_test`,
shifted so the newest detection is a few minutes old, and places one clearly labelled test
facility on the most recent event. The normal analysis and alert engine then run, so the
resulting alert travels the real path: alert engine -> event bus -> WebSocket -> UI.

Safeguards:
  * refused unless DATA_MODE=test-fixture, APP_ENV != production and the database name ends in _test;
  * replayed detections carry source_mode='test_fixture'; the test facility is named
    "TEST FIXTURE ..." with tags {"fixture": "true"};
  * a live-mode API refuses to start if any test_fixture row exists in its database.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from app.config import REPO_ROOT, Settings, get_settings
from app.core.errors import ForbiddenError
from app.db.engine import connection, transaction

log = logging.getLogger(__name__)

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "firms_viirs_snpp_sample.csv"
FIXTURE_PRODUCT = "VIIRS_SNPP_NRT"
TEST_FACILITY_NAME = "TEST FIXTURE refinery (not a real site)"


def test_mode_problems(settings: Settings) -> list[str]:
    problems = []
    if not settings.test_fixture_mode:
        problems.append("DATA_MODE is not 'test-fixture'")
    if settings.is_production:
        problems.append("test fixtures are never allowed in production")
    name = settings.database_name or ""
    if not name.endswith("_test"):
        problems.append(f"database '{name}' is not a dedicated test database (name must end in _test)")
    if not Path(FIXTURE).exists():
        problems.append("fixture file is not available in this deployment")
    return problems


def assert_test_mode() -> Settings:
    settings = get_settings()
    problems = test_mode_problems(settings)
    if problems:
        raise ForbiddenError("Test-fixture replay is not allowed: " + "; ".join(problems))
    return settings


def live_database_contains_fixtures() -> bool:
    with connection() as conn:
        return bool(conn.execute(text("SELECT EXISTS (SELECT 1 FROM thermal_observations WHERE source_mode = 'test_fixture')")).scalar_one())


def replay() -> dict:
    """Ingest the labelled fixture, analyse, attach the test facility, analyse again."""
    from app.analytics.pipeline import run_analysis
    from app.db.runs import finish_run, start_run
    from app.geo.boundary import get_monitoring_area
    from app.ingestion.firms.parser import parse_firms_csv
    from app.ingestion.firms.repository import insert_observations

    settings = assert_test_mode()
    reset()  # every replay starts from an empty test database, so it always yields a fresh alert
    parsed = parse_firms_csv(FIXTURE.read_text(encoding="utf-8"), FIXTURE_PRODUCT, region=get_monitoring_area())
    run_id = start_run("firms_ingest", "nasa_firms", {"mode": "test_fixture", "fixture": FIXTURE.name})
    with transaction() as conn:
        inserted = insert_observations(conn, parsed.observations, mode="test_fixture", run_id=run_id)
        # Shift the fixture so its newest detection is 5 minutes old (test database only).
        conn.execute(
            text(
                """
                UPDATE thermal_observations
                   SET acquired_at = acquired_at + d.shift,
                       acq_date = ((acquired_at + d.shift) AT TIME ZONE 'UTC')::date,
                       acq_time = to_char((acquired_at + d.shift) AT TIME ZONE 'UTC', 'HH24MI')
                  FROM (SELECT now() - interval '5 minutes' - max(acquired_at) AS shift
                          FROM thermal_observations WHERE source_mode = 'test_fixture') d
                 WHERE source_mode = 'test_fixture'
                """
            )
        )
    finish_run(run_id, "success", fetched=len(parsed.observations), valid=len(parsed.observations), inserted=inserted,
               details={"mode": "test_fixture"})

    # Wider windows so the whole (week-long) sample is analysed.
    analysis_settings = settings.model_copy(update={"cluster_window_days": 60, "persistence_lookback_days": 60,
                                                    "landcover_enabled": False})
    run_analysis(analysis_settings)
    with transaction() as conn:
        c = conn.execute(
            text("SELECT center_latitude AS lat, center_longitude AS lon FROM thermal_clusters "
                 "WHERE status = 'active' ORDER BY end_time DESC, observation_count DESC LIMIT 1")
        ).mappings().one()
        conn.execute(
            text(
                """
                INSERT INTO industrial_facilities (source_id, source_ref, name, facility_type, latitude, longitude, geom, tags)
                VALUES ('osm_overpass', 'test/fixture-1', :name, 'refinery', :lat, :lon,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, '{"fixture": "true"}')
                ON CONFLICT (source_id, source_ref) DO NOTHING
                """
            ),
            {"name": TEST_FACILITY_NAME, "lat": c["lat"], "lon": c["lon"]},
        )
    summary = run_analysis(analysis_settings)
    alerts = (summary.get("incidents") or {}).get("alerts_created", 0)
    log.info("test fixture replayed", extra={"inserted": inserted, "alerts_created": alerts})
    return {"mode": "test_fixture", "detections_inserted": inserted, "alerts_created": alerts,
            "incidents": summary.get("incidents")}


def reset() -> dict:
    """Empty the test database's event data (detections, clusters, incidents, alerts) and the
    test facility. Only reachable on a *_test database in test-fixture mode."""
    assert_test_mode()
    with transaction() as conn:
        conn.execute(text("TRUNCATE notifications, alerts, incidents, cluster_facility_proximity RESTART IDENTITY CASCADE"))
        conn.execute(text("UPDATE thermal_observations SET cluster_id = NULL"))
        conn.execute(text("TRUNCATE thermal_clusters RESTART IDENTITY CASCADE"))
        n = conn.execute(text("DELETE FROM thermal_observations")).rowcount
        f = conn.execute(text("DELETE FROM industrial_facilities WHERE tags ->> 'fixture' = 'true'")).rowcount
    return {"detections_removed": n, "facilities_removed": f}
