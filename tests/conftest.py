"""Shared fixtures. Unit tests never touch the network or a database."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def viirs_csv() -> str:
    return (FIXTURES / "firms_viirs_snpp_sample.csv").read_text(encoding="utf-8")


@pytest.fixture
def modis_csv() -> str:
    return (FIXTURES / "firms_modis_sample.csv").read_text(encoding="utf-8")


@pytest.fixture
def no_database(monkeypatch):
    """Force the app to run without DATABASE_URL (even if a developer .env defines one)."""
    from app.config import get_settings

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("AUTO_MIGRATE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
