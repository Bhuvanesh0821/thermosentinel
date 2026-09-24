"""Application configuration loaded from environment variables / .env files.

Secrets (DATABASE_URL, NASA_FIRMS_MAP_KEY, ADMIN_API_TOKEN) are only ever read here
and are never returned by any API endpoint.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.geo.region import BBox

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

FIRMS_PRODUCTS_ALLOWED = {
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
    "MODIS_NRT",
}

PRIORITY_ORDER = ["low", "medium", "high", "critical"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application -------------------------------------------------------------
    app_env: str = "development"
    log_level: str = "INFO"
    log_format: str = "json"  # json | text
    # Browser origins allowed for REST (CORS) and WebSocket connections. In production set
    # FRONTEND_URL; CORS_ORIGINS adds extra origins (comma-separated).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
    # Public URLs of the deployed frontend and API (used for CORS and links in e-mail/webhook alerts).
    frontend_url: str | None = None
    backend_url: str | None = None
    # "live" (default): real NASA FIRMS data only. "test-fixture": a clearly labelled replay of the
    # recorded FIRMS sample for demonstrations - only on a separate database named *_test, never
    # in production (see docs and app/demo/fixture.py).
    data_mode: str = "live"
    # How long startup keeps retrying the database (e.g. while a suspended Neon compute wakes).
    db_startup_retry_seconds: int = Field(60, ge=5, le=3600)
    admin_api_token: SecretStr | None = None
    auto_migrate: bool = True
    scheduler_enabled: bool = True
    http_user_agent: str = "ThermoSentinel/0.1 (geospatial thermal intelligence prototype)"

    # --- Database (Neon PostgreSQL + PostGIS) ----------------------------------
    database_url: SecretStr | None = None
    db_pool_size: int = Field(5, ge=1, le=50)
    db_max_overflow: int = Field(5, ge=0, le=50)
    migrations_dir: Path = REPO_ROOT / "database" / "migrations"

    # --- Region of interest ------------------------------------------------------
    # India only: official-claim land boundary + EEZ (see data_pipeline/build_india_boundary.py).
    # All records outside this polygon are discarded at ingestion.
    region_name: str = "India"
    region_boundary_file: Path = REPO_ROOT / "database" / "boundaries" / "india_monitoring_area.geojson"
    # Optional override of the fetch/tiling extent (west,south,east,north). Defaults to the
    # bounding box of the boundary file. Records are still clipped to the polygon.
    region_bbox: str | None = None

    # --- NASA FIRMS --------------------------------------------------------------
    nasa_firms_map_key: SecretStr | None = None
    firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov"
    firms_products: str = "VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT,MODIS_NRT"
    firms_day_range: int = Field(2, ge=1, le=5)
    firms_backfill_days: int = Field(10, ge=0, le=60)
    firms_public_feed_region: str = "South_Asia"
    firms_public_feed_window: str = "7d"  # 24h | 48h | 7d
    firms_poll_minutes: int = Field(60, ge=10)

    # --- OpenStreetMap / Overpass -------------------------------------------------
    overpass_urls: str = (
        "https://overpass-api.de/api/interpreter,"
        "https://overpass.private.coffee/api/interpreter,"
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    )
    overpass_tile_deg: float = Field(6.0, gt=0.5, le=30)
    overpass_timeout_s: int = Field(180, ge=30, le=900)
    # Parallel tile queries. Public Overpass allows 4 slots per client; 2 is polite and ~2x faster.
    overpass_concurrency: int = Field(2, ge=1, le=3)
    facilities_refresh_hours: int = Field(168, ge=1)

    # --- Land cover (ESA WorldCover) ---------------------------------------------
    landcover_enabled: bool = True
    landcover_worldcover_base_url: str = (
        "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
    )
    landcover_sample_radius_m: int = Field(250, ge=50, le=2000)
    landcover_target_resolution_m: float = Field(40.0, ge=10, le=320)
    landcover_max_samples_per_run: int = Field(300, ge=0, le=5000)
    landcover_workers: int = Field(6, ge=1, le=16)

    # --- Clustering ---------------------------------------------------------------
    cluster_eps_km: float = Field(1.5, gt=0.1, le=20)
    cluster_max_gap_hours: float = Field(72.0, gt=1, le=720)
    cluster_min_samples: int = Field(1, ge=1, le=20)
    cluster_window_days: int = Field(10, ge=1, le=60)

    # --- Persistence -------------------------------------------------------------
    persistence_radius_m: int = Field(1000, ge=100, le=10000)
    persistence_lookback_days: int = Field(30, ge=2, le=365)
    persistence_min_days_persistent: int = Field(5, ge=2)
    persistence_min_coverage_days: int = Field(5, ge=2)
    persistence_min_ratio: float = Field(0.25, gt=0, le=1)

    # --- Industrial proximity ------------------------------------------------------
    proximity_search_radius_m: int = Field(10000, ge=1000, le=50000)
    proximity_near_m: int = Field(1000, ge=100)
    proximity_assoc_m: int = Field(3000, ge=200)

    # --- Classification -------------------------------------------------------------
    # Only the transparent rule-based baseline exists. A trained model can be registered later
    # (see app/analytics/classifier.py); no model is claimed before validated training data exists.
    classifier: str = "rules"

    # --- Incidents / alert engine ------------------------------------------------------
    incident_min_score: float = Field(40.0, ge=0, le=100)
    alert_min_priority: str = "medium"
    alert_rule_high_frp_mw: float = Field(50.0, gt=0)             # high thermal intensity (24 h max FRP)
    alert_rule_repeat_min_24h: int = Field(5, ge=2)               # repeated observations in 24 h
    alert_rule_spike_factor: float = Field(3.0, ge=1.5)           # unusual activity vs location baseline
    alert_rule_spike_min_24h: int = Field(4, ge=2)
    alert_rule_high_confidence_min_frp: float = Field(10.0, ge=0)  # high-confidence detection with real heat
    alert_rules_disabled: str = ""                                # comma-separated rule keys to switch off

    # --- Notifications (credentials stay server-side) ---------------------------------
    notify_webhook_url: str | None = None
    notify_webhook_min_severity: str = "high"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    notify_email_to: str | None = None  # comma-separated recipients
    notify_email_min_severity: str = "high"

    # --- Search -------------------------------------------------------------------
    geocoder_url: str = "https://nominatim.openstreetmap.org/search"
    geocoder_enabled: bool = True

    # --- Retention (keeps Neon free-tier storage in check) ------------------------
    observation_retention_days: int = Field(120, ge=7)

    @field_validator("data_mode")
    @classmethod
    def _check_data_mode(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("live", "test-fixture"):
            raise ValueError("DATA_MODE must be 'live' or 'test-fixture'")
        return v

    @field_validator("alert_min_priority", "notify_webhook_min_severity", "notify_email_min_severity")
    @classmethod
    def _check_priority(cls, v: str) -> str:
        if v not in PRIORITY_ORDER:
            raise ValueError(f"alert_min_priority must be one of {PRIORITY_ORDER}")
        return v

    @field_validator("firms_public_feed_window")
    @classmethod
    def _check_window(cls, v: str) -> str:
        if v not in {"24h", "48h", "7d"}:
            raise ValueError("firms_public_feed_window must be 24h, 48h or 7d")
        return v

    @field_validator("region_bbox")
    @classmethod
    def _check_bbox(cls, v: str | None) -> str | None:
        if v:
            BBox.parse(v)
        return v or None

    @field_validator("firms_products")
    @classmethod
    def _check_products(cls, v: str) -> str:
        products = [p.strip() for p in v.split(",") if p.strip()]
        unknown = set(products) - FIRMS_PRODUCTS_ALLOWED
        if unknown:
            raise ValueError(f"Unsupported FIRMS products: {sorted(unknown)}")
        return v

    # --- Derived helpers ---------------------------------------------------------
    @property
    def bbox(self) -> BBox:
        """Fetch / tiling extent. Clipping always uses the exact India polygon."""
        if self.region_bbox:
            return BBox.parse(self.region_bbox)
        from app.geo.boundary import get_monitoring_area

        return get_monitoring_area().bbox

    @property
    def firms_product_list(self) -> list[str]:
        return [p.strip() for p in self.firms_products.split(",") if p.strip()]

    @property
    def overpass_url_list(self) -> list[str]:
        return [u.strip() for u in self.overpass_urls.split(",") if u.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]
        if self.frontend_url and self.frontend_url.strip():
            origins.append(self.frontend_url.strip().rstrip("/"))
        return list(dict.fromkeys(origins))

    def production_problems(self) -> list[str]:
        """Configuration errors that make a production start unsafe or non-functional."""
        problems = []
        if not self.is_production:
            return problems
        if not self.database_url_value:
            problems.append("DATABASE_URL is not set")
        if not self.admin_token_value or len(self.admin_token_value) < 24:
            problems.append("ADMIN_API_TOKEN must be set (>= 24 characters) to protect pipeline triggers")
        if not self.frontend_url:
            problems.append("FRONTEND_URL is not set (browser CORS / WebSocket origin)")
        insecure = [o for o in self.cors_origin_list if o.startswith("http://") and "localhost" not in o and "127.0.0.1" not in o]
        if insecure:
            problems.append(f"non-HTTPS browser origins configured: {insecure}")
        if "*" in self.cors_origin_list:
            problems.append("wildcard CORS origin is not allowed")
        if self.data_mode != "live":
            problems.append("DATA_MODE must be 'live' in production (test fixtures are development-only)")
        return problems

    def frontend_link(self, path: str) -> str | None:
        return f"{self.frontend_url.rstrip('/')}{path}" if self.frontend_url else None

    @property
    def firms_mode(self) -> str:
        """'api' when a MAP_KEY is configured, otherwise the keyless public NRT feed."""
        return "api" if self.firms_map_key else "public_feed"

    @property
    def firms_map_key(self) -> str | None:
        if self.nasa_firms_map_key is None:
            return None
        value = self.nasa_firms_map_key.get_secret_value().strip()
        return value or None

    @property
    def database_url_value(self) -> str | None:
        if self.database_url is None:
            return None
        value = self.database_url.get_secret_value().strip()
        return value or None

    @property
    def admin_token_value(self) -> str | None:
        if self.admin_api_token is None:
            return None
        value = self.admin_api_token.get_secret_value().strip()
        return value or None

    @property
    def disabled_alert_rules(self) -> set[str]:
        return {r.strip() for r in self.alert_rules_disabled.split(",") if r.strip()}

    @property
    def email_recipients(self) -> list[str]:
        return [r.strip() for r in (self.notify_email_to or "").split(",") if r.strip()]

    @property
    def smtp_password_value(self) -> str | None:
        return self.smtp_password.get_secret_value() if self.smtp_password else None

    @property
    def test_fixture_mode(self) -> bool:
        return self.data_mode == "test-fixture"

    @property
    def database_name(self) -> str | None:
        url = self.database_url_value
        if not url:
            return None
        return url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] or None

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
