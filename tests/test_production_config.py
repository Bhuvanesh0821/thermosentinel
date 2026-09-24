"""Production hardening: unsafe configuration is refused, CORS derives from FRONTEND_URL, and
failure messages never leak credentials."""

from app.config import Settings
from app.core.observability import failure_summary, record_failure, redact


def prod(**kw):
    base = dict(_env_file=None, app_env="production", database_url="postgresql://u:p@db.example/x",
                admin_api_token="x" * 32, frontend_url="https://thermosentinel.vercel.app", cors_origins="")
    base.update(kw)
    return Settings(**base)


def test_valid_production_config_has_no_problems():
    s = prod()
    assert s.production_problems() == []
    assert s.cors_origin_list == ["https://thermosentinel.vercel.app"]


def test_production_refuses_missing_or_weak_settings():
    assert any("DATABASE_URL" in p for p in prod(database_url=None).production_problems())
    assert any("ADMIN_API_TOKEN" in p for p in prod(admin_api_token="short").production_problems())
    assert any("FRONTEND_URL" in p for p in prod(frontend_url=None).production_problems())
    assert any("wildcard" in p for p in prod(cors_origins="*").production_problems())
    assert any("non-HTTPS" in p for p in prod(cors_origins="http://evil.example").production_problems())


def test_development_is_not_validated_and_keeps_local_origins():
    s = Settings(_env_file=None, app_env="development")
    assert s.production_problems() == []
    assert "http://localhost:5173" in s.cors_origin_list


def test_frontend_url_is_merged_without_duplicates_or_trailing_slash():
    s = prod(cors_origins="https://thermosentinel.vercel.app/,https://extra.example", frontend_url="https://thermosentinel.vercel.app/")
    assert s.cors_origin_list == ["https://thermosentinel.vercel.app", "https://extra.example"]
    assert s.frontend_link("/investigation/7") == "https://thermosentinel.vercel.app/investigation/7"


def test_redaction_masks_credentials():
    assert "secretpw" not in redact("could not connect to postgresql://neondb_owner:secretpw@ep-x.neon.tech/neondb")
    assert "abc123" not in redact("GET https://firms.modaps.eosdis.nasa.gov/api/area/csv/abc123/VIIRS map_key=abc123")


def test_failures_are_counted_per_category():
    before = {c["key"]: c["total_since_start"] for c in failure_summary()["categories"]}
    record_failure("realtime", "WebSocket origin rejected: https://evil.example")
    after = {c["key"]: c for c in failure_summary()["categories"]}
    assert after["realtime"]["total_since_start"] == before["realtime"] + 1
    assert after["realtime"]["last_error"].startswith("WebSocket origin rejected")


def test_test_fixture_mode_is_confined_to_test_databases():
    from app.demo.fixture import test_mode_problems

    ok = Settings(_env_file=None, data_mode="test-fixture", database_url="postgresql://u@127.0.0.1:55432/thermosentinel_test")
    assert test_mode_problems(ok) == []
    live_db = Settings(_env_file=None, data_mode="test-fixture", database_url="postgresql://u:p@ep-x.neon.tech/neondb?sslmode=require")
    assert any("not a dedicated test database" in p for p in test_mode_problems(live_db))
    assert any("DATA_MODE" in p for p in prod(data_mode="test-fixture").production_problems())
    assert any("never allowed in production" in p for p in test_mode_problems(prod(data_mode="test-fixture")))
