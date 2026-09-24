"""End-to-end database tests (PostgreSQL + PostGIS), run on real FIRMS fixture rows.

Skipped unless TEST_DATABASE_URL points at a dedicated, disposable database whose name ends in
`_test` - the schema is dropped and recreated. Example (local server):

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/thermosentinel_test pytest tests/test_db_integration.py
"""

import os

import pytest
from sqlalchemy import text

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_URL.rstrip("/").split("?")[0].endswith("_test"),
    reason="set TEST_DATABASE_URL to a disposable database whose name ends in _test",
)


@pytest.fixture(scope="module")
def db(viirs_csv_module):
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", TEST_URL)
    mp.setenv("LANDCOVER_ENABLED", "false")  # no network in tests
    mp.setenv("SCHEDULER_ENABLED", "false")
    from app.config import get_settings
    from app.db import engine as engine_mod

    get_settings.cache_clear()
    engine_mod.dispose_engine()
    eng = engine_mod.get_engine()
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    from app.db.migrate import apply_migrations
    from app.geo.region_sync import sync_monitoring_region
    from app.jobs import ensure_data_source_registry

    result = apply_migrations()
    ensure_data_source_registry()
    sync_monitoring_region()
    yield {"migrations": result}
    engine_mod.dispose_engine()
    get_settings.cache_clear()
    mp.undo()


@pytest.fixture(scope="module")
def viirs_csv_module():
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / "firms_viirs_snpp_sample.csv").read_text(encoding="utf-8")


def _ingest(csv_text):
    from app.db.engine import transaction
    from app.db.runs import start_run
    from app.geo.boundary import get_monitoring_area
    from app.ingestion.firms.parser import parse_firms_csv
    from app.ingestion.firms.repository import insert_observations

    parsed = parse_firms_csv(csv_text, "VIIRS_SNPP_NRT", region=get_monitoring_area())
    run_id = start_run("firms_ingest", "nasa_firms", {"test": True})
    with transaction() as conn:
        return len(parsed.observations), insert_observations(conn, parsed.observations, mode="public_feed", run_id=run_id)


def test_migrations_create_schema(db):
    assert [m for m in db["migrations"]["applied"]] == sorted(db["migrations"]["applied"])
    from app.db.engine import connection

    with connection() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}
        postgis = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")).scalar_one()
    assert postgis
    for t in ("thermal_observations", "industrial_facilities", "land_cover", "thermal_clusters", "incidents", "alerts",
              "notifications", "data_sources", "system_events", "monitoring_regions", "facility_tiles"):
        assert t in tables


def test_ingest_is_idempotent_and_india_only(db, viirs_csv_module):
    valid, inserted = _ingest(viirs_csv_module)
    assert valid == 30 and inserted == 30
    _, again = _ingest(viirs_csv_module)
    assert again == 0
    from app.db.engine import connection

    with connection() as conn:
        outside = conn.execute(
            text(
                "SELECT count(*) FROM thermal_observations o WHERE NOT ST_Covers("
                "(SELECT geom FROM monitoring_regions WHERE role = 'monitoring_area'), o.geom)"
            )
        ).scalar_one()
    assert outside == 0


def test_analysis_end_to_end_and_stable_ids(db, viirs_csv_module):
    from app.analytics.pipeline import run_analysis
    from app.db.engine import connection

    # Fixture rows are from the last 7-8 days of the feed; widen the window so all are analysed.
    os.environ["CLUSTER_WINDOW_DAYS"] = "60"
    os.environ["PERSISTENCE_LOOKBACK_DAYS"] = "60"
    from app.config import get_settings

    get_settings.cache_clear()
    first = run_analysis()
    assert first["clustering"]["observations"] == 30
    with connection() as conn:
        unclustered = conn.execute(text("SELECT count(*) FROM thermal_observations WHERE cluster_id IS NULL")).scalar_one()
        rows = conn.execute(
            text(
                "SELECT id, persistence_category, classification, risk_score, priority, intelligence "
                "FROM thermal_clusters WHERE status = 'active' ORDER BY id"
            )
        ).mappings().all()
    assert unclustered == 0
    assert rows and all(r["persistence_category"] and r["classification"] and r["priority"] for r in rows)
    assert all(0 <= r["risk_score"] <= 100 for r in rows)
    assert all("confirmed" not in r["classification"] for r in rows)
    assert all(r["intelligence"]["factors"] for r in rows)

    second = run_analysis()
    with connection() as conn:
        ids_after = [r[0] for r in conn.execute(text("SELECT id FROM thermal_clusters WHERE status = 'active' ORDER BY id"))]
    assert ids_after == [r["id"] for r in rows]  # cluster identity is stable across runs
    assert second["clustering"]["new"] == 0
    os.environ.pop("CLUSTER_WINDOW_DAYS")
    os.environ.pop("PERSISTENCE_LOOKBACK_DAYS")
    get_settings.cache_clear()


# ------------------------------------------------------------------ Stage 2: alerts & API
# Controlled fixture: one test-only facility (clearly marked, never shipped) placed on the
# most recent real fixture cluster so the rule engine has an industrial event to evaluate.


@pytest.fixture(scope="module")
def incident_ready(db, viirs_csv_module):
    from app.analytics.pipeline import run_analysis
    from app.db.engine import connection, transaction
    from app.config import get_settings

    os.environ["CLUSTER_WINDOW_DAYS"] = "60"
    os.environ["PERSISTENCE_LOOKBACK_DAYS"] = "60"
    os.environ["LANDCOVER_ENABLED"] = "false"
    os.environ["GEOCODER_ENABLED"] = "false"
    os.environ["ALERT_MIN_PRIORITY"] = "low"
    os.environ["INCIDENT_MIN_SCORE"] = "0"
    get_settings.cache_clear()
    _ingest(viirs_csv_module)
    # Fixture rows are days old; shift them (test DB only) so the newest is one hour old and the
    # incident is still open, as it would be for live FIRMS data.
    with transaction() as conn:
        conn.execute(
            text(
                "UPDATE thermal_observations SET acquired_at = acquired_at + d.shift, "
                "acq_date = ((acquired_at + d.shift) AT TIME ZONE 'UTC')::date, "
                "acq_time = to_char((acquired_at + d.shift) AT TIME ZONE 'UTC', 'HH24MI') "
                "FROM (SELECT now() - interval '1 hour' - max(acquired_at) AS shift FROM thermal_observations) d"
            )
        )
    run_analysis()
    with connection() as conn:
        c = conn.execute(
            text("SELECT id, center_latitude AS lat, center_longitude AS lon FROM thermal_clusters "
                 "WHERE status = 'active' ORDER BY end_time DESC, observation_count DESC, id LIMIT 1")
        ).mappings().one()
    with transaction() as conn:
        conn.execute(
            text(
                """
                INSERT INTO industrial_facilities (source_id, source_ref, name, facility_type, latitude, longitude, geom, tags)
                VALUES ('osm_overpass', 'test/1', 'TEST FIXTURE refinery', 'refinery', :lat, :lon,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, '{"fixture": "true"}')
                ON CONFLICT DO NOTHING
                """
            ),
            {"lat": c["lat"], "lon": c["lon"]},
        )
    run_analysis()
    with connection() as conn:
        cid = conn.execute(
            text("SELECT cluster_id FROM incidents WHERE status <> 'closed' ORDER BY last_detected_at DESC LIMIT 1")
        ).scalar_one()
    yield cid
    for k in ("CLUSTER_WINDOW_DAYS", "PERSISTENCE_LOOKBACK_DAYS", "GEOCODER_ENABLED", "ALERT_MIN_PRIORITY", "INCIDENT_MIN_SCORE"):
        os.environ.pop(k, None)
    get_settings.cache_clear()


def test_alert_generated_once_per_incident(incident_ready):
    from app.alerts.service import update_incidents_and_alerts
    from app.db.engine import connection

    with connection() as conn:
        inc = conn.execute(text("SELECT id, classification FROM incidents WHERE cluster_id = :c"), {"c": incident_ready}).mappings().one()
        alerts = conn.execute(text("SELECT id, rules, evidence, status FROM alerts WHERE incident_id = :i"), {"i": inc["id"]}).mappings().all()
    assert inc["classification"] in {"gas_flare_like", "persistent_industrial_source", "industrial_associated_event"}
    assert len(alerts) == 1
    a = alerts[0]
    assert a["rules"] and "industrial_proximity" in a["rules"]
    assert a["evidence"]["rules"] and all("threshold" in r for r in a["evidence"]["rules"])

    # Re-evaluating the same evidence must not create a duplicate.
    update_incidents_and_alerts([incident_ready])
    update_incidents_and_alerts([incident_ready])
    with connection() as conn:
        n = conn.execute(text("SELECT count(*) FROM alerts WHERE incident_id = :i"), {"i": inc["id"]}).scalar_one()
        notes = conn.execute(
            text("SELECT event, count(*) FROM notifications WHERE alert_id = :a AND channel = 'in_app' GROUP BY event"), {"a": a["id"]}
        ).all()
    assert n == 1
    assert all(cnt == 1 for _e, cnt in notes)  # one notification per alert event, never repeated


def test_database_rejects_second_open_alert(incident_ready):
    import sqlalchemy.exc

    from app.db.engine import transaction

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        with transaction() as conn:
            conn.execute(
                text(
                    "INSERT INTO alerts (incident_id, cluster_id, alert_type, severity, title, description, status, evidence) "
                    "SELECT id, cluster_id, 'event', 'low', 'dup', 'dup', 'open', '{}'::jsonb FROM incidents WHERE cluster_id = :c"
                ),
                {"c": incident_ready},
            )


def test_stage2_endpoints(incident_ready):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        alerts = client.get("/api/alerts", params={"status": "open"}).json()
        assert alerts["meta"]["total"] >= 1 and alerts["meta"]["by_status"]["open"] >= 1
        al = alerts["data"][0]
        assert {"alert_id", "incident_id", "severity", "status", "title", "description", "location", "facility", "source",
                "created_at", "acknowledged_at", "resolved_at", "rules"} <= set(al)
        bd = client.get("/api/alerts", params={"status": "open", "breakdown": "true"}).json()["meta"]["breakdown"]
        assert sum(bd["by_severity"].values()) == alerts["meta"]["total"]
        assert bd["by_rule"].get("industrial_proximity", 0) >= 1
        ib = client.get("/api/incidents", params={"breakdown": "true"}).json()["meta"]["breakdown"]
        assert sum(ib["by_priority"].values()) == sum(c["count"] for c in ib["by_classification"]) >= 1
        detail = client.get(f"/api/alerts/{al['id']}").json()["data"]
        assert detail["evidence"]["rules"]

        inv = client.get(f"/api/investigations/{al['incident_id']}").json()["data"]
        assert inv["observations"] and inv["timeline"] and inv["classification"]["rationale"]
        assert inv["classification"]["classifier"]["trained_model"] is False

        intel = client.get(f"/api/clusters/{incident_ready}/intelligence").json()["data"]
        assert 0 <= intel["intelligence_score"] <= 100 and intel["risk_level"]

        ov = client.get("/api/analytics/overview", params={"days": 90}).json()["data"]
        assert sum(d["total"] for d in ov["observations_daily"]) == ov["totals"]["detections"]
        grid = client.get("/api/analytics/grid", params={"days": 90}).json()
        assert sum(f["properties"]["detections"] for f in grid["data"]["features"]) == ov["totals"]["detections"]

        health = client.get("/api/system/health").json()["data"]
        assert {c["status"] for c in health["components"]} <= {"connected", "degraded", "unavailable"}
        assert "database" in {c["key"] for c in health["components"]}

        found = client.get("/api/search", params={"q": "TEST FIXTURE", "types": "facilities"}).json()["data"]
        assert found["facilities"] and found["facilities"][0]["label"].startswith("TEST FIXTURE")

        v = client.post("/api/voice/interpret", json={"text": "How many open alerts are there?"}).json()["data"]
        assert v["supported"] and v["data"]["open"] == alerts["meta"]["by_status"]["open"]
        v = client.post("/api/voice/interpret", json={"text": "Open the latest alert"}).json()["data"]
        assert v["action"]["path"].startswith("/investigation/")

        ack = client.post(f"/api/alerts/{al['id']}/acknowledge").json()["data"]
        assert ack["status"] == "acknowledged"
        res = client.post(f"/api/alerts/{al['id']}/resolve", json={"note": "test"}).json()["data"]
        assert res["status"] == "resolved"
        assert client.get("/api/alerts/999999999").status_code == 404


def test_operator_resolution_is_not_re_raised(incident_ready):
    """After an operator resolves an alert (previous test, via the API), the same evidence must
    not raise a new alert for that incident."""
    from app.alerts.service import update_incidents_and_alerts
    from app.db.engine import connection

    stats = update_incidents_and_alerts([incident_ready])
    with connection() as conn:
        rows = conn.execute(text("SELECT status, resolved_by FROM alerts WHERE cluster_id = :c ORDER BY id"), {"c": incident_ready}).all()
    assert rows == [("resolved", "operator")]
    assert stats["alerts_suppressed"] == 1 and stats["alerts_created"] == 0


def test_incident_closes_when_event_no_longer_qualifies(incident_ready):
    """Re-analysis that drops an event below the incident criteria closes its incident and
    resolves its alert with the reason (instead of leaving a stale open incident)."""
    from app.alerts.service import update_incidents_and_alerts
    from app.db.engine import connection, transaction

    with transaction() as conn:
        conn.execute(text("UPDATE alerts SET status = 'open', resolved_at = NULL, resolution = NULL WHERE cluster_id = :c"),
                     {"c": incident_ready})
        # Re-analysis now says it is crop burning (a non-incident class).
        conn.execute(text("UPDATE thermal_clusters SET classification = 'agricultural_burning' WHERE id = :c"), {"c": incident_ready})
    stats = update_incidents_and_alerts([incident_ready])
    with connection() as conn:
        inc = conn.execute(text("SELECT status, classification FROM incidents WHERE cluster_id = :c"), {"c": incident_ready}).mappings().one()
        al = conn.execute(text("SELECT status, resolution FROM alerts WHERE cluster_id = :c"), {"c": incident_ready}).mappings().one()
    assert inc["status"] == "closed" and inc["classification"] == "agricultural_burning"
    assert al["status"] == "resolved" and "no longer meets the incident criteria" in al["resolution"]
    assert stats["alerts_resolved"] >= 1
