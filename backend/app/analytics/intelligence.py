"""Explainable intelligence engine v2: evidence -> indicators -> score, risk level, classification.

Design principles
* Every indicator is computed from stored real evidence (FIRMS detections, OSM facilities,
  ESA WorldCover, persistence history). Nothing is asserted that the evidence cannot support.
* Missing evidence is excluded and the remaining weights are renormalised - absence of data
  neither raises nor lowers the score - and is listed as a caveat.
* Classification comes from a pluggable classifier (app/analytics/classifier.py); today a
  transparent rule-based baseline, never presented as a trained model.
* Each indicator's value, normalised score, weight and contribution is returned so an analyst
  can audit the result. Methodology: docs/intelligence-methodology.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.analytics.classifier import CLASSES, INCIDENT_CLASSES, ClassificationResult, get_classifier
from app.analytics.features import ClusterEvidence
from app.ingestion.facilities.classify import FACILITY_TYPES, THERMAL_RELEVANCE

ENGINE_VERSION = "ts-intel-2.0"

# Backwards-compatible aliases used across the codebase.
CLASSIFICATION_LABELS = CLASSES
__all__ = ["ClusterEvidence", "assess", "Assessment", "INCIDENT_CLASSES", "CLASSIFICATION_LABELS", "WEIGHTS", "ENGINE_VERSION"]

WEIGHTS = {
    "industrial_proximity": 0.18,
    "temporal_persistence": 0.16,
    "frp": 0.15,
    "thermal_intensity": 0.08,
    "observation_frequency": 0.08,
    "facility_type": 0.08,
    "satellite_confidence": 0.08,
    "spatial_concentration": 0.08,
    "land_cover_context": 0.07,
    "night_detection": 0.04,
}

RELATIONSHIP_SCORE = {"inside_footprint": 1.0, "adjacent": 0.85, "nearby": 0.55, "distant": 0.15, "none": 0.0}
PERSISTENCE_SCORE = {"persistent": 1.0, "recurring": 0.6, "insufficient_history": 0.3, "transient": 0.15}
RISK_LEVELS = ("low", "medium", "high", "critical")

FRP_SATURATION_MW = 300.0
BRIGHTNESS_FLOOR_K, BRIGHTNESS_CEIL_K = 300.0, 400.0
FREQUENCY_SATURATION = 10.0  # detections per coverage day
CONCENTRATION_SCALE_KM = 0.75


@dataclass
class Assessment:
    classification: ClassificationResult
    risk_score: float
    priority: str
    factors: list[dict]
    evidence: list[str]
    hypotheses: list[str]
    caveats: list[str]

    # Convenience accessors used by the pipeline.
    @property
    def classification_key(self) -> str:
        return self.classification.key

    @property
    def evidence_strength(self) -> str:
        return self.classification.evidence_strength

    def as_dict(self) -> dict:
        clf = get_classifier()
        return {
            "engine_version": ENGINE_VERSION,
            "intelligence_score": self.risk_score,
            "risk_level": self.priority,
            "classification": self.classification.key,
            "classification_label": self.classification.label,
            "evidence_strength": self.classification.evidence_strength,
            "classification_rationale": self.classification.rationale,
            "alternatives_rejected": self.classification.rejected,
            "classifier": {"name": clf.name, "version": clf.version, "kind": clf.kind, "trained_model": clf.trained},
            "risk_score": self.risk_score,
            "priority": self.priority,
            "factors": self.factors,
            "evidence": self.evidence,
            "hypotheses": self.hypotheses,
            "caveats": self.caveats,
        }


def _facility_label(ev: ClusterEvidence) -> str:
    type_label = FACILITY_TYPES.get(ev.facility_type or "", "industrial facility")
    name = ev.facility_name or f"unnamed {type_label.lower()}"
    ref = f", OSM {ev.facility_ref}" if ev.facility_ref else ""
    return f"{name} ({type_label}{ref})"


def _factor(key: str, label: str, value: str, score: float | None, note: str) -> dict:
    return {
        "key": key,
        "label": label,
        "value": value,
        "score": None if score is None else round(max(0.0, min(1.0, score)), 3),
        "weight": WEIGHTS[key],
        "available": score is not None,
        "note": note,
    }


def indicators(ev: ClusterEvidence) -> list[dict]:
    rel = ev.relationship
    relevance = THERMAL_RELEVANCE.get(ev.facility_type or "", 0.0) if rel != "none" else 0.0
    freq = ev.frequency_per_day
    extent = ev.extent_km
    multi = ev.observation_count > 1
    return [
        _factor(
            "frp",
            "Fire radiative power (max FRP)",
            f"{ev.max_frp:.1f} MW (mean {ev.avg_frp or 0:.1f})" if ev.max_frp is not None else "not reported",
            (math.log10(1 + ev.max_frp) / math.log10(1 + FRP_SATURATION_MW)) if ev.max_frp is not None else None,
            f"Log-scaled; saturates at {FRP_SATURATION_MW:.0f} MW.",
        ),
        _factor(
            "thermal_intensity",
            "Thermal intensity (brightness temperature)",
            f"{ev.max_brightness:.1f} K" if ev.max_brightness is not None else "not reported",
            ((ev.max_brightness - BRIGHTNESS_FLOOR_K) / (BRIGHTNESS_CEIL_K - BRIGHTNESS_FLOOR_K)) if ev.max_brightness is not None else None,
            f"Peak mid-infrared brightness temperature, scaled {BRIGHTNESS_FLOOR_K:.0f}-{BRIGHTNESS_CEIL_K:.0f} K.",
        ),
        _factor(
            "observation_frequency",
            "Observation frequency",
            f"{freq:.1f} detections / day of coverage ({ev.observations_nearby} in total)" if freq is not None else "not computed",
            (math.log1p(freq) / math.log1p(FREQUENCY_SATURATION)) if freq is not None else None,
            f"Detections within the persistence radius per day of FIRMS data held; saturates at {FREQUENCY_SATURATION:.0f}/day.",
        ),
        _factor(
            "temporal_persistence",
            "Temporal persistence",
            (
                f"{ev.persistence_category} ({ev.persistence_detection_days}/{ev.persistence_coverage_days} days)"
                if ev.persistence_category
                else "not computed"
            ),
            PERSISTENCE_SCORE.get(ev.persistence_category) if ev.persistence_category else None,
            ev.persistence_explanation or "Distinct detection days near this location.",
        ),
        _factor(
            "industrial_proximity",
            "Proximity to industrial facility",
            (
                f"{rel.replace('_', ' ')} - {ev.facility_distance_m:,.0f} m to {_facility_label(ev)}"
                if rel != "none" and ev.facility_distance_m is not None
                else "no mapped facility within 10 km"
            ),
            RELATIONSHIP_SCORE.get(rel, 0.0),
            "Inside outline 1.0 · <=1 km 0.85 · <=3 km 0.55 · <=10 km 0.15 · none 0.",
        ),
        _factor(
            "facility_type",
            "Industrial facility type",
            FACILITY_TYPES.get(ev.facility_type or "", "none") + (f" (relevance {relevance:.2f})" if relevance else ""),
            relevance,
            "Plausibility that this facility type emits satellite-observable heat (flare/refinery/steel 1.0 ... generic works 0.4).",
        ),
        _factor(
            "satellite_confidence",
            "Satellite detection confidence",
            f"{ev.mean_confidence:.2f}" if ev.mean_confidence is not None else "not reported",
            ev.mean_confidence,
            "Mean FIRMS confidence (VIIRS low/nominal/high = 0.3/0.6/0.9; MODIS % / 100).",
        ),
        _factor(
            "spatial_concentration",
            "Spatial concentration",
            f"{ev.observation_count} detections within {extent:.2f} km" if (multi and extent is not None) else "single detection",
            (1.0 / (1.0 + extent / CONCENTRATION_SCALE_KM)) if (multi and extent is not None) else None,
            "Compact, repeated heat (stacks, flares, furnaces) scores high; heat spread over a large area (field burning) low.",
        ),
        _factor(
            "land_cover_context",
            "Land-cover context",
            (
                f"{ev.land_cover_dominant or 'mixed'}; built-up+bare {ev.built_bare:.0%}, cropland {ev.cropland:.0%}, vegetation {ev.vegetation:.0%}"
                if ev.land_cover_ok
                else ("open sea / no land pixels" if ev.offshore else "not available")
            ),
            min(1.0, ev.built_bare * 1.25) if ev.land_cover_ok else None,
            "Share of built-up / bare land (ESA WorldCover) around the detection - typical of industrial sites.",
        ),
        _factor(
            "night_detection",
            "Night-time detections",
            f"{ev.night:.0%} of detections at night",
            ev.night_fraction,
            "Flares and furnaces are detected at night; most agricultural fires burn by day.",
        ),
    ]


def _risk_level(score: float, ev: ClusterEvidence) -> str:
    if score >= 80 and ev.strongly_associated:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def assess(ev: ClusterEvidence) -> Assessment:
    factors = indicators(ev)
    available_weight = sum(f["weight"] for f in factors if f["available"]) or 1.0
    score = 0.0
    for f in factors:
        contribution = 100.0 * f["weight"] * f["score"] / available_weight if f["available"] else 0.0
        f["contribution"] = round(contribution, 2)
        score += contribution
    risk_score = round(min(100.0, max(0.0, score)), 1)

    classification = get_classifier().classify(ev)

    evidence: list[str] = []
    caveats = ["Inferred from satellite thermal detections and open geospatial data; not a confirmed ground observation."]
    if ev.associated and ev.facility_distance_m is not None:
        where = "Inside the mapped footprint of" if ev.relationship == "inside_footprint" else f"{ev.facility_distance_m:,.0f} m from"
        evidence.append(f"{where} {_facility_label(ev)}.")
        if ev.facility_member_share is not None and ev.facility_member_share < 0.5:
            caveats.append(
                f"Only {ev.facility_member_share:.0%} of this cluster's detections lie within the association radius of the facility."
            )
    elif ev.relationship == "distant" and ev.facility_distance_m is not None:
        evidence.append(f"Nearest mapped facility is {ev.facility_distance_m / 1000:.1f} km away: {_facility_label(ev)}.")
    else:
        evidence.append("No mapped industrial facility within 10 km (OSM coverage may be incomplete).")
    if ev.persistence_explanation:
        evidence.append(ev.persistence_explanation)
    if ev.max_frp is not None:
        evidence.append(f"{ev.observation_count} detection(s); peak FRP {ev.max_frp:.1f} MW.")
    if ev.land_cover_ok:
        evidence.append(f"Land cover (ESA WorldCover): predominantly {ev.land_cover_dominant or 'mixed'}.")
    elif ev.offshore:
        evidence.append("Offshore: no land-cover pixels at this location (within India's EEZ).")
    else:
        caveats.append("Land-cover context not yet available for this location.")
    if ev.persistence_category == "insufficient_history":
        caveats.append("Too little FIRMS history is stored to judge recurrence yet.")

    hypotheses: list[str] = []
    key = classification.key
    if key == "gas_flare_like":
        hypotheses.append("Pattern consistent with routine or emergency gas flaring; FIRMS cannot confirm the cause.")
    elif key == "mining_associated":
        hypotheses.append("Possible coal-seam, overburden-dump or mine-fire heat; FIRMS cannot distinguish the cause.")
    elif key in ("persistent_industrial_source", "industrial_associated_event"):
        if ev.facility_type in ("steel_plant", "metal_smelter", "cement_plant", "brick_kiln"):
            hypotheses.append("Consistent with a high-temperature industrial process (furnace, converter or kiln).")
        elif ev.facility_type == "thermal_power_plant":
            hypotheses.append("Power stations seldom register in FIRMS; possible sources include coal-yard or ash-pond fires.")
    elif key == "persistent_unattributed_source":
        hypotheses.append("Persistent heat with no mapped facility may indicate unmapped industry or flaring.")
    if ev.associated and ev.cropland >= 0.6 and not ev.recurring:
        caveats.append("Surroundings are predominantly cropland; agricultural burning near the facility cannot be excluded.")

    return Assessment(
        classification=classification,
        risk_score=risk_score,
        priority=_risk_level(risk_score, ev),
        factors=factors,
        evidence=evidence,
        hypotheses=hypotheses,
        caveats=caveats,
    )
