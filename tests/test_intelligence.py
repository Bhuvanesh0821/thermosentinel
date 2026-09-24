"""Explainable intelligence engine v2: hedged labels, renormalised weights, auditable factors,
rule-based classification with rationale and rejected alternatives."""

from app.analytics.classifier import CLASSES, INCIDENT_CLASSES, RuleBasedClassifier, get_classifier
from app.analytics.intelligence import CLASSIFICATION_LABELS, WEIGHTS, ClusterEvidence, assess


def evidence(**overrides):
    base = dict(
        observation_count=6,
        max_frp=45.0,
        avg_frp=20.0,
        night_fraction=0.6,
        mean_confidence=0.6,
        detection_days=5,
        persistence_category="persistent",
        persistence_detection_days=6,
        persistence_coverage_days=7,
        persistence_ratio=0.86,
        persistence_explanation="Detected on 6 of 7 days.",
        spatial_relationship="inside_footprint",
        facility_distance_m=0.0,
        facility_type="refinery",
        facility_name="Example refinery name from OSM",
        facility_ref="way/1",
        facility_member_share=1.0,
        land_cover_status="ok",
        land_cover_fractions={"50": 0.8, "60": 0.1, "40": 0.1},
        land_cover_dominant="Built-up",
        extent_radius_m=400.0,
        observations_nearby=30,
    )
    base.update(overrides)
    return ClusterEvidence(**base)


NO_FACILITY = dict(spatial_relationship="none", facility_distance_m=None, facility_type=None, facility_name=None,
                   facility_ref=None, facility_member_share=None)


def test_refinery_night_recurring_heat_is_gas_flare_like():
    a = assess(evidence())
    assert a.classification_key == "gas_flare_like"
    assert a.priority in {"high", "critical"}
    assert a.evidence_strength == "high"
    assert a.classification.rationale
    assert all(r["reason"].startswith("Not selected") for r in a.classification.rejected)


def test_non_hydrocarbon_persistent_source():
    a = assess(evidence(facility_type="steel_plant", facility_name="Steel works"))
    assert a.classification_key == "persistent_industrial_source"


def test_mining_association():
    a = assess(evidence(facility_type="mining", persistence_category="transient", land_cover_fractions={"60": 0.6, "50": 0.4}))
    assert a.classification_key == "mining_associated"


def test_coastal_power_plant_is_not_offshore_flare():
    """Regression: heat at a coastal (water-dominated) power station must not be labelled a flare."""
    a = assess(evidence(facility_type="thermal_power_plant", land_cover_fractions={"80": 0.7, "50": 0.3}))
    assert a.classification_key != "gas_flare_like"


def test_offshore_recurring_heat_without_facility_is_flare_like():
    a = assess(evidence(**NO_FACILITY, land_cover_status="no_data", land_cover_fractions={}))
    assert a.classification_key == "gas_flare_like"


def test_labels_are_hedged():
    for label in CLASSIFICATION_LABELS.values():
        assert "confirm" not in label.lower()
    a = assess(evidence())
    assert "not a confirmed" in a.caveats[0]


def test_agricultural_context_without_facility():
    a = assess(evidence(**NO_FACILITY, persistence_category="transient", night_fraction=0.0,
                        land_cover_fractions={"40": 0.85, "10": 0.15}, land_cover_dominant="Cropland"))
    assert a.classification_key == "agricultural_burning"
    assert a.classification_key not in INCIDENT_CLASSES
    assert a.priority in {"low", "medium"}


def test_transient_fire_near_site_in_cropland_is_agricultural():
    a = assess(evidence(spatial_relationship="nearby", facility_distance_m=2500, facility_type="cement_plant",
                        persistence_category="transient", night_fraction=0.0, land_cover_fractions={"40": 0.8, "50": 0.2}))
    assert a.classification_key == "agricultural_burning"


def test_vegetation_fire():
    a = assess(evidence(**NO_FACILITY, persistence_category="transient", land_cover_fractions={"10": 0.7, "20": 0.3}))
    assert a.classification_key == "vegetation_fire"


def test_persistent_source_without_mapped_facility():
    a = assess(evidence(**NO_FACILITY))
    assert a.classification_key == "persistent_unattributed_source"


def test_unclassified_when_evidence_is_insufficient():
    a = assess(evidence(**NO_FACILITY, persistence_category="transient", land_cover_status=None, land_cover_fractions={}))
    assert a.classification_key == "unclassified_anomaly"
    assert any("Land-cover" in r for r in a.classification.rationale)


def test_missing_land_cover_is_excluded_not_penalised():
    with_lc = assess(evidence(land_cover_fractions={"50": 0.5, "40": 0.5}))
    without = assess(evidence(land_cover_status=None, land_cover_fractions={}))
    lc = next(f for f in without.factors if f["key"] == "land_cover_context")
    assert lc["available"] is False and lc["contribution"] == 0
    total = sum(f["contribution"] for f in without.factors)
    assert abs(total - without.risk_score) < 0.2
    assert with_lc.risk_score != without.risk_score


def test_factor_weights_sum_to_one_and_are_reported():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
    a = assess(evidence())
    assert {f["key"] for f in a.factors} == set(WEIGHTS)
    assert "spatial_concentration" in WEIGHTS
    assert 0 <= a.risk_score <= 100


def test_api_payload_exposes_score_level_and_classifier_honestly():
    d = assess(evidence()).as_dict()
    assert d["intelligence_score"] == d["risk_score"]
    assert d["risk_level"] in {"low", "medium", "high", "critical"}
    assert d["classifier"]["trained_model"] is False
    assert d["classifier"]["kind"] == "rule-based baseline"
    assert d["classification_rationale"] and isinstance(d["alternatives_rejected"], list)


def test_critical_requires_strong_association():
    a = assess(evidence(spatial_relationship="nearby", facility_distance_m=2500))
    assert a.priority != "critical"


def test_classifier_registry():
    clf = get_classifier("rules")
    assert isinstance(clf, RuleBasedClassifier)
    assert set(CLASSES) >= INCIDENT_CLASSES
