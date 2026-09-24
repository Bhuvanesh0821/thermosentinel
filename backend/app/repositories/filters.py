"""Tiny helper for composing parameterised WHERE clauses."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.geo.region import BBox


@dataclass
class Where:
    clauses: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)

    def add(self, clause: str, **params) -> "Where":
        self.clauses.append(clause)
        self.params.update(params)
        return self

    def bbox(self, column: str, bbox: BBox | None, prefix: str = "bb") -> "Where":
        if bbox is not None:
            self.add(
                f"ST_Intersects({column}, ST_MakeEnvelope(:{prefix}_w, :{prefix}_s, :{prefix}_e, :{prefix}_n, 4326)::geography)",
                **{f"{prefix}_w": bbox.west, f"{prefix}_s": bbox.south, f"{prefix}_e": bbox.east, f"{prefix}_n": bbox.north},
            )
        return self

    @property
    def sql(self) -> str:
        return ("WHERE " + " AND ".join(self.clauses)) if self.clauses else ""


def point_feature(fid, lat: float, lon: float, properties: dict) -> dict:
    return {
        "type": "Feature",
        "id": fid,
        "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
        "properties": properties,
    }


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}
