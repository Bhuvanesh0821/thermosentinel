"""FIRMS CSV parsing, normalisation, validation and India clipping (real FIRMS rows)."""

import pytest

from app.core.errors import UpstreamError
from app.geo.boundary import get_monitoring_area
from app.ingestion.firms.client import FirmsClient
from app.ingestion.firms.parser import parse_firms_csv


def test_viirs_rows_are_clipped_to_india(viirs_csv):
    result = parse_firms_csv(viirs_csv, "VIIRS_SNPP_NRT", region=get_monitoring_area())
    assert result.total_rows == 40
    assert len(result.observations) == 30
    assert result.out_of_region == 10
    assert result.rejected == 0
    area = get_monitoring_area()
    assert all(area.contains(o.latitude, o.longitude) for o in result.observations)


def test_viirs_normalisation(viirs_csv):
    obs = parse_firms_csv(viirs_csv, "VIIRS_SNPP_NRT").observations[0]
    assert obs.instrument == "VIIRS"  # public feed has no instrument column
    assert obs.satellite_name == "Suomi NPP"
    assert obs.confidence_level in {"low", "nominal", "high"}
    assert obs.confidence_pct is None
    assert len(obs.acq_time) == 4 and obs.acquired_at.tzinfo is not None
    assert obs.source_record_key.startswith("VIIRS_SNPP_NRT|")
    assert obs.brightness and obs.brightness > 200  # Kelvin


def test_modis_confidence_is_mapped_from_percent(modis_csv):
    result = parse_firms_csv(modis_csv, "MODIS_NRT")
    for obs in result.observations:
        assert obs.instrument == "MODIS"
        assert obs.confidence_pct is not None
        expected = "low" if obs.confidence_pct < 30 else ("nominal" if obs.confidence_pct < 80 else "high")
        assert obs.confidence_level == expected


def test_duplicate_rows_are_counted_not_stored(viirs_csv):
    lines = viirs_csv.strip().splitlines()
    doubled = "\n".join(lines + lines[1:6])
    result = parse_firms_csv(doubled, "VIIRS_SNPP_NRT")
    assert result.duplicates_in_batch == 5
    assert len(result.observations) == 40


def test_invalid_rows_are_rejected(viirs_csv):
    header, first = viirs_csv.splitlines()[:2]
    bad = first.split(",")
    bad[0] = "123.0"  # latitude out of range
    result = parse_firms_csv("\n".join([header, first, ",".join(bad)]), "VIIRS_SNPP_NRT")
    assert len(result.observations) == 1
    assert result.rejected == 1 and result.errors


def test_missing_columns_reported():
    result = parse_firms_csv("foo,bar\n1,2\n", "VIIRS_SNPP_NRT")
    assert not result.observations and "missing required columns" in result.errors[0]


@pytest.mark.parametrize("body", ["Invalid MAP_KEY.", "", "   "])
def test_firms_plain_text_errors_are_detected(body):
    with pytest.raises(UpstreamError):
        FirmsClient._check_csv(body, "test")
