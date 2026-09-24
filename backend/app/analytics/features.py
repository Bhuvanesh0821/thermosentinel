"""Event features: the measured evidence for one thermal event (cluster).

Every field is derived from stored real data (FIRMS detections, OSM facilities, ESA
WorldCover, persistence history). Missing evidence is `None`, never guessed. The same
feature set feeds the rule-based classifier today and any trained model later
(`ml/export_features.py` exports it for labelling).
"""

from __future__ import annotations

from dataclasses import dataclass, field

HYDROCARBON_TYPES = {"gas_flare", "oil_gas_facility", "refinery", "lng_terminal", "petrochemical"}
LC_BUILT, LC_BARE, LC_CROP, LC_WATER = "50", "60", "40", "80"
LC_VEGETATION = ("10", "20", "30", "90", "95")
ASSOCIATED = ("inside_footprint", "adjacent", "nearby")
STRONG = ("inside_footprint", "adjacent")


@dataclass
class ClusterEvidence:
    observation_count: int
    max_frp: float | None
    avg_frp: float | None
    night_fraction: float | None
    mean_confidence: float | None
    detection_days: int
    persistence_category: str | None
    persistence_detection_days: int | None
    persistence_coverage_days: int | None
    persistence_ratio: float | None
    persistence_explanation: str | None
    spatial_relationship: str | None
    facility_distance_m: float | None
    facility_type: str | None
    facility_name: str | None
    facility_ref: str | None
    facility_member_share: float | None
    land_cover_status: str | None
    land_cover_fractions: dict[str, float] = field(default_factory=dict)
    land_cover_dominant: str | None = None
    max_brightness: float | None = None  # K
    extent_radius_m: float | None = None
    observations_nearby: int | None = None  # detections within the persistence radius over the lookback

    # ------------------------------------------------------------ derived views
    @property
    def relationship(self) -> str:
        return self.spatial_relationship or "none"

    @property
    def associated(self) -> bool:
        return self.relationship in ASSOCIATED

    @property
    def strongly_associated(self) -> bool:
        return self.relationship in STRONG

    @property
    def land_cover_ok(self) -> bool:
        return self.land_cover_status == "ok" and bool(self.land_cover_fractions)

    def lc(self, *codes: str) -> float:
        return float(sum(self.land_cover_fractions.get(c, 0.0) for c in codes)) if self.land_cover_ok else 0.0

    @property
    def cropland(self) -> float:
        return self.lc(LC_CROP)

    @property
    def vegetation(self) -> float:
        return self.lc(*LC_VEGETATION)

    @property
    def built_bare(self) -> float:
        return self.lc(LC_BUILT, LC_BARE)

    @property
    def bare(self) -> float:
        return self.lc(LC_BARE)

    @property
    def offshore(self) -> bool:
        """At sea: WorldCover has no land pixels here, or water dominates."""
        return self.land_cover_status == "no_data" or (self.land_cover_ok and self.lc(LC_WATER) >= 0.5)

    @property
    def recurring(self) -> bool:
        return self.persistence_category in ("recurring", "persistent")

    @property
    def persistent(self) -> bool:
        return self.persistence_category == "persistent"

    @property
    def night(self) -> float:
        return self.night_fraction or 0.0

    @property
    def extent_km(self) -> float | None:
        return None if self.extent_radius_m is None else self.extent_radius_m / 1000.0

    @property
    def frequency_per_day(self) -> float | None:
        """Detections per day of FIRMS coverage at this location."""
        if self.observations_nearby is None or not self.persistence_coverage_days:
            return None
        return self.observations_nearby / self.persistence_coverage_days

    def as_feature_row(self) -> dict:
        """Flat numeric/categorical features (for export and future model training)."""
        return {
            "observation_count": self.observation_count,
            "max_frp": self.max_frp,
            "avg_frp": self.avg_frp,
            "max_brightness": self.max_brightness,
            "night_fraction": self.night_fraction,
            "mean_confidence": self.mean_confidence,
            "detection_days": self.detection_days,
            "persistence_category": self.persistence_category,
            "persistence_ratio": self.persistence_ratio,
            "frequency_per_day": self.frequency_per_day,
            "extent_km": self.extent_km,
            "relationship": self.relationship,
            "facility_distance_m": self.facility_distance_m,
            "facility_type": self.facility_type,
            "facility_member_share": self.facility_member_share,
            "lc_cropland": self.cropland if self.land_cover_ok else None,
            "lc_vegetation": self.vegetation if self.land_cover_ok else None,
            "lc_built_bare": self.built_bare if self.land_cover_ok else None,
            "offshore": self.offshore,
        }
