"""Event classification framework.

`Classifier` is the contract. Today the only implementation is `RuleBasedClassifier`, a
transparent, feature-based baseline: every decision lists the conditions that were met and
why the closest alternatives were rejected. No trained model is claimed - there is no
validated, labelled training set yet. When one exists, a `ModelClassifier` implementing the
same interface can be registered in `CLASSIFIERS` and selected with `CLASSIFIER=<name>`
without touching the pipeline, API or UI.

Labels are deliberately hedged ("possible", "-like", "-associated"): satellite heat plus
open geospatial context supports an inference, not a confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.analytics.features import HYDROCARBON_TYPES, ClusterEvidence
from app.ingestion.facilities.classify import FACILITY_TYPES, THERMAL_RELEVANCE

CLASSES: dict[str, str] = {
    "gas_flare_like": "Gas-flare-like activity",
    "mining_associated": "Mining-associated thermal activity",
    "persistent_industrial_source": "Persistent industrial thermal source",
    "industrial_associated_event": "Industrial-associated thermal event",
    "persistent_unattributed_source": "Persistent thermal source (no mapped facility)",
    "agricultural_burning": "Possible agricultural burning",
    "vegetation_fire": "Possible wildfire / vegetation fire",
    "unclassified_anomaly": "Unclassified thermal anomaly",
}

# Classes that open incidents (industrial or persistent heat worth monitoring).
INCIDENT_CLASSES = {
    "gas_flare_like",
    "mining_associated",
    "persistent_industrial_source",
    "industrial_associated_event",
    "persistent_unattributed_source",
}


@dataclass
class ClassificationResult:
    key: str
    label: str
    evidence_strength: str  # low | medium | high
    rationale: list[str]
    rejected: list[dict] = field(default_factory=list)  # [{"class", "label", "reason"}]


class Classifier(Protocol):
    name: str
    version: str
    kind: str  # "rule-based baseline" | "trained model"
    trained: bool

    def classify(self, ev: ClusterEvidence) -> ClassificationResult: ...


def _facility(ev: ClusterEvidence) -> str:
    type_label = FACILITY_TYPES.get(ev.facility_type or "", "industrial facility")
    return f"{ev.facility_name or 'unnamed ' + type_label.lower()} ({type_label.lower()})"


def _dist(ev: ClusterEvidence) -> str:
    if ev.relationship == "inside_footprint":
        return "inside the mapped outline of"
    return f"{ev.facility_distance_m:,.0f} m from" if ev.facility_distance_m is not None else "near"


class RuleBasedClassifier:
    name = "ts-rules"
    version = "2.0"
    kind = "rule-based baseline"
    trained = False

    def classify(self, ev: ClusterEvidence) -> ClassificationResult:
        relevance = THERMAL_RELEVANCE.get(ev.facility_type or "", 0.0) if ev.associated else 0.0
        extent = ev.extent_km
        compact = extent is None or extent <= 1.5
        checks: list[tuple[str, bool, list[str], str]] = []

        # 1. Gas-flare-like: hydrocarbon site (or offshore), recurring, night heat, compact.
        hydro = ev.associated and ev.facility_type in HYDROCARBON_TYPES
        # Offshore heat counts only when no other (non-hydrocarbon) facility explains it,
        # e.g. not a coastal power station.
        flare_site = hydro or (ev.offshore and ev.recurring and not ev.associated)
        flare_ok = flare_site and ev.recurring and ev.night >= 0.3 and compact
        checks.append((
            "gas_flare_like",
            flare_ok,
            [
                f"{_dist(ev).capitalize()} {_facility(ev)}" if hydro else "Offshore location (no land pixels / open water)",
                f"Recurring heat ({ev.persistence_category})",
                f"{ev.night:.0%} of detections at night (flares burn around the clock)",
                "Spatially compact source" + (f" ({extent:.2f} km extent)" if extent is not None else ""),
            ],
            "needs a hydrocarbon site or offshore location, recurring heat, >=30% night detections and a compact source",
        ))

        # 2. Mining-associated.
        mining = ev.associated and ev.facility_type == "mining"
        checks.append((
            "mining_associated",
            mining,
            [f"{_dist(ev).capitalize()} {_facility(ev)}"]
            + ([f"{ev.bare:.0%} bare / sparse land cover"] if ev.bare >= 0.3 else []),
            "needs a mapped mining area within the association radius",
        ))

        # 3. Persistent industrial source.
        pis = ev.associated and relevance >= 0.6 and ev.persistent
        checks.append((
            "persistent_industrial_source",
            pis,
            [
                f"{_dist(ev).capitalize()} {_facility(ev)}",
                f"Thermally relevant facility type (relevance {relevance:.2f})",
                ev.persistence_explanation or "Persistent heat",
            ],
            "needs a thermally relevant facility within 3 km and persistent (not just recurring) heat",
        ))

        # Cropland guard: a transient fire merely *near* a site, in farmland, is more likely a crop fire.
        crop_guard = ev.relationship == "nearby" and ev.cropland >= 0.6 and not ev.recurring

        # 4. Industrial-associated event.
        iae = ev.associated and relevance >= 0.4 and not crop_guard
        checks.append((
            "industrial_associated_event",
            iae,
            [f"{_dist(ev).capitalize()} {_facility(ev)}", f"Facility thermal relevance {relevance:.2f}"],
            "needs a thermally relevant mapped facility within 3 km (and not a transient fire in surrounding cropland)",
        ))

        # 5. Persistent source with no mapped facility.
        pus = ev.persistent and not ev.associated
        checks.append((
            "persistent_unattributed_source",
            pus,
            [ev.persistence_explanation or "Persistent heat", "No mapped industrial facility within 3 km (OSM may be incomplete)"],
            "needs persistent heat without a mapped facility nearby",
        ))

        # 6. Agricultural burning.
        agri = ev.land_cover_ok and ev.cropland >= 0.5 and not ev.persistent and (not ev.associated or crop_guard)
        checks.append((
            "agricultural_burning",
            agri,
            [f"{ev.cropland:.0%} cropland around the detection (ESA WorldCover)", "Not persistent"]
            + (["Mostly daytime detections"] if ev.night < 0.3 else []),
            "needs >=50% cropland, non-persistent heat and no stronger industrial evidence",
        ))

        # 7. Wildfire / vegetation fire.
        veg = ev.land_cover_ok and ev.vegetation >= 0.5 and not ev.persistent and not ev.associated
        checks.append((
            "vegetation_fire",
            veg,
            [f"{ev.vegetation:.0%} tree/shrub/grass/wetland cover (ESA WorldCover)", "Not persistent", "No mapped facility within 3 km"],
            "needs >=50% natural vegetation, non-persistent heat and no mapped facility nearby",
        ))

        chosen = next(((k, r) for k, ok, r, _ in checks if ok), None)
        if chosen is None:
            key = "unclassified_anomaly"
            reasons = ["Available evidence does not meet the criteria of any specific class"]
            if not ev.land_cover_ok:
                reasons.append("Land-cover context not yet available")
        else:
            key, reasons = chosen
        rejected = [
            {"class": k, "label": CLASSES[k], "reason": f"Not selected: {why}"}
            for k, ok, _r, why in checks
            if k != key and not ok
        ][:4]

        return ClassificationResult(
            key=key,
            label=CLASSES[key],
            evidence_strength=self._strength(key, ev, relevance),
            rationale=[r for r in reasons if r],
            rejected=rejected,
        )

    @staticmethod
    def _strength(key: str, ev: ClusterEvidence, relevance: float) -> str:
        """Counts independent, converging evidence lines; contradicting ones subtract."""
        pts = 0
        if key in ("gas_flare_like", "mining_associated", "persistent_industrial_source", "industrial_associated_event"):
            pts += 2 if ev.strongly_associated else (1 if ev.associated else 0)
            pts += 1 if ev.recurring else 0
            pts += 1 if ev.built_bare >= 0.4 or ev.offshore else 0
            pts += 1 if ev.night >= 0.3 else 0
            pts += 1 if ev.observation_count >= 3 else 0
            pts -= 1 if (ev.cropland >= 0.6 or ev.vegetation >= 0.6) else 0
            pts -= 1 if (ev.facility_member_share is not None and ev.facility_member_share < 0.5) else 0
        elif key == "persistent_unattributed_source":
            pts += 1 + (1 if (ev.persistence_ratio or 0) >= 0.5 else 0) + (1 if ev.built_bare >= 0.4 else 0)
        elif key in ("agricultural_burning", "vegetation_fire"):
            dominant = ev.cropland if key == "agricultural_burning" else ev.vegetation
            pts += 1 + (1 if dominant >= 0.7 else 0) + (1 if ev.night < 0.2 else 0)
            pts -= 1 if ev.recurring else 0
        return "high" if pts >= 4 else ("medium" if pts >= 2 else "low")


CLASSIFIERS: dict[str, Classifier] = {"rules": RuleBasedClassifier()}


def get_classifier(name: str = "rules") -> Classifier:
    if name not in CLASSIFIERS:
        raise ValueError(
            f"Classifier '{name}' is not available. Registered: {sorted(CLASSIFIERS)}. "
            "A trained model must be added to CLASSIFIERS before it can be selected."
        )
    return CLASSIFIERS[name]
