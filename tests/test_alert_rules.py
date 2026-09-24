"""Alert rule engine: each rule fires only on its measured threshold and records the evidence;
severity escalation is bounded (critical needs a strong facility link)."""

import pytest

from app.alerts.rules import RULES, RecentActivity, evaluate, severity_for
from app.config import Settings


@pytest.fixture
def settings():
    return Settings(_env_file=None, database_url="", alert_rule_high_frp_mw=50, alert_rule_repeat_min_24h=5,
                    alert_rule_spike_factor=3.0, alert_rule_spike_min_24h=4, alert_rule_high_confidence_min_frp=10)


def incident(**kw):
    base = dict(persistence_category="transient", persistence_detection_days=1, persistence_coverage_days=7,
                spatial_relationship="none", facility_relevance=0.0, facility_name=None, facility_distance_m=None)
    base.update(kw)
    return base


def recent(**kw):
    base = dict(detections_24h=1, max_frp_24h=5.0, high_confidence_24h=0, prior_detections=0, prior_days=0)
    base.update(kw)
    return RecentActivity(**base)


def keys(hits):
    return {h.key for h in hits}


def test_quiet_event_fires_nothing(settings):
    assert evaluate(incident(), recent(), settings) == []


def test_high_intensity_threshold_is_inclusive(settings):
    assert "high_intensity" not in keys(evaluate(incident(), recent(max_frp_24h=49.9), settings))
    hits = evaluate(incident(), recent(max_frp_24h=50.0), settings)
    hit = next(h for h in hits if h.key == "high_intensity")
    assert hit.value == 50.0 and hit.threshold == 50
    assert hit.label == RULES["high_intensity"]


def test_repeated_and_persistent(settings):
    hits = evaluate(incident(persistence_category="persistent", persistence_detection_days=6), recent(detections_24h=5), settings)
    assert {"repeated_observations", "persistent_activity"} <= keys(hits)


def test_industrial_proximity_needs_strong_link_and_relevance(settings):
    near = incident(spatial_relationship="adjacent", facility_relevance=0.9, facility_name="X", facility_distance_m=300)
    assert "industrial_proximity" in keys(evaluate(near, recent(), settings))
    assert "industrial_proximity" not in keys(evaluate({**near, "spatial_relationship": "nearby"}, recent(), settings))
    assert "industrial_proximity" not in keys(evaluate({**near, "facility_relevance": 0.4}, recent(), settings))


def test_unusual_activity_uses_location_baseline(settings):
    # baseline 1/day over 6 days: 4 detections in 24 h is >= 3x baseline and >= min 4
    assert "unusual_activity" in keys(evaluate(incident(), recent(detections_24h=4, prior_detections=6, prior_days=6), settings))
    # baseline 2/day: 4 is below 3x
    assert "unusual_activity" not in keys(evaluate(incident(), recent(detections_24h=4, prior_detections=12, prior_days=6), settings))
    # no history: no baseline, no spike claim
    assert "unusual_activity" not in keys(evaluate(incident(), recent(detections_24h=9), settings))


def test_high_confidence(settings):
    assert "high_confidence" in keys(evaluate(incident(), recent(high_confidence_24h=2), settings))


def test_rules_can_be_disabled():
    s = Settings(_env_file=None, database_url="", alert_rules_disabled="high_intensity, repeated_observations")
    hits = evaluate(incident(), recent(max_frp_24h=500, detections_24h=50), s)
    assert not {"high_intensity", "repeated_observations"} & keys(hits)


def test_severity_escalation_is_bounded(settings):
    hi = evaluate(incident(), recent(max_frp_24h=80), settings)
    assert severity_for("medium", [], False) == "medium"
    assert severity_for("medium", hi, False) == "high"
    # critical requires a strong (inside / adjacent) facility association
    assert severity_for("high", hi, False) == "high"
    assert severity_for("high", hi, True) == "critical"
    assert severity_for("critical", hi, True) == "critical"
    # non-escalating rules never raise severity
    rep = evaluate(incident(), recent(detections_24h=9), settings)
    assert severity_for("medium", rep, True) == "medium"
