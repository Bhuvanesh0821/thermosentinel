"""Alert rules (pure functions; thresholds from settings).

Each rule inspects real, stored evidence for one incident and, when it fires, records the
measured value and the threshold it crossed so the alert is fully auditable. Rules can be
switched off with ALERT_RULES_DISABLED.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.config import PRIORITY_ORDER, Settings

RULES: dict[str, str] = {
    "high_intensity": "High thermal intensity",
    "repeated_observations": "Repeated observations",
    "persistent_activity": "Persistent activity",
    "industrial_proximity": "Industrial proximity",
    "unusual_activity": "Unusual temporal behaviour",
    "high_confidence": "High-confidence detection",
}
# Rules whose firing raises the alert one severity level above the incident priority.
ESCALATING_RULES = {"high_intensity", "unusual_activity"}
RANK = {p: i for i, p in enumerate(PRIORITY_ORDER)}


@dataclass
class RecentActivity:
    detections_24h: int
    max_frp_24h: float | None
    high_confidence_24h: int
    prior_detections: int  # near the location, earlier in the persistence lookback
    prior_days: int  # days of FIRMS coverage those prior detections span

    @property
    def baseline_per_day(self) -> float | None:
        return self.prior_detections / self.prior_days if self.prior_days > 0 else None


@dataclass
class RuleHit:
    key: str
    label: str
    detail: str
    value: float | int | str | None
    threshold: float | int | str | None

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate(incident: dict, recent: RecentActivity, settings: Settings) -> list[RuleHit]:
    """`incident` needs: persistence_category, persistence_detection_days, persistence_coverage_days,
    spatial_relationship, facility_relevance, facility_name, facility_distance_m."""
    off = settings.disabled_alert_rules
    hits: list[RuleHit] = []

    if "high_intensity" not in off and recent.max_frp_24h is not None and recent.max_frp_24h >= settings.alert_rule_high_frp_mw:
        hits.append(RuleHit(
            "high_intensity", RULES["high_intensity"],
            f"Peak FRP {recent.max_frp_24h:.1f} MW in the last 24 h (threshold {settings.alert_rule_high_frp_mw:.0f} MW)",
            round(recent.max_frp_24h, 1), settings.alert_rule_high_frp_mw,
        ))

    if "repeated_observations" not in off and recent.detections_24h >= settings.alert_rule_repeat_min_24h:
        hits.append(RuleHit(
            "repeated_observations", RULES["repeated_observations"],
            f"{recent.detections_24h} detections in the last 24 h (threshold {settings.alert_rule_repeat_min_24h})",
            recent.detections_24h, settings.alert_rule_repeat_min_24h,
        ))

    if "persistent_activity" not in off and incident.get("persistence_category") == "persistent":
        hits.append(RuleHit(
            "persistent_activity", RULES["persistent_activity"],
            f"Heat on {incident.get('persistence_detection_days')} of {incident.get('persistence_coverage_days')} days of FIRMS coverage",
            incident.get("persistence_detection_days"), "persistent",
        ))

    rel = incident.get("spatial_relationship")
    if "industrial_proximity" not in off and rel in ("inside_footprint", "adjacent") and (incident.get("facility_relevance") or 0) >= 0.6:
        where = "inside the mapped outline of" if rel == "inside_footprint" else f"{incident.get('facility_distance_m') or 0:,.0f} m from"
        hits.append(RuleHit(
            "industrial_proximity", RULES["industrial_proximity"],
            f"Heat {where} {incident.get('facility_name') or 'a mapped facility'}",
            rel, "inside or <= 1 km",
        ))

    base = recent.baseline_per_day
    if (
        "unusual_activity" not in off
        and base is not None
        and recent.detections_24h >= settings.alert_rule_spike_min_24h
        and recent.detections_24h >= settings.alert_rule_spike_factor * max(base, 0.5)
    ):
        hits.append(RuleHit(
            "unusual_activity", RULES["unusual_activity"],
            f"{recent.detections_24h} detections in 24 h vs a baseline of {base:.1f}/day over the previous {recent.prior_days} days",
            recent.detections_24h, f">= {settings.alert_rule_spike_factor:g} x baseline",
        ))

    if "high_confidence" not in off and recent.high_confidence_24h > 0:
        hits.append(RuleHit(
            "high_confidence", RULES["high_confidence"],
            f"{recent.high_confidence_24h} high-confidence detection(s) with FRP >= {settings.alert_rule_high_confidence_min_frp:.0f} MW in the last 24 h",
            recent.high_confidence_24h, f"high confidence, FRP >= {settings.alert_rule_high_confidence_min_frp:.0f} MW",
        ))
    return hits


def severity_for(priority: str, hits: list[RuleHit], strongly_associated: bool) -> str:
    """Incident priority, raised one level by an escalating rule (critical requires a facility link)."""
    rank = RANK.get(priority, 0)
    if any(h.key in ESCALATING_RULES for h in hits):
        rank += 1
    if rank >= RANK["critical"] and not strongly_associated:
        rank = RANK["high"]
    return PRIORITY_ORDER[min(rank, RANK["critical"])]
