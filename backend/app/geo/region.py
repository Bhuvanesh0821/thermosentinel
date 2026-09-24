"""Region-of-interest bounding boxes and tiling helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    @classmethod
    def parse(cls, value: str) -> "BBox":
        parts = [p.strip() for p in value.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must be 'west,south,east,north'")
        try:
            west, south, east, north = (float(p) for p in parts)
        except ValueError as exc:
            raise ValueError("bbox values must be numeric") from exc
        if not (-180 <= west < east <= 180):
            raise ValueError("bbox longitudes must satisfy -180 <= west < east <= 180")
        if not (-90 <= south < north <= 90):
            raise ValueError("bbox latitudes must satisfy -90 <= south < north <= 90")
        return cls(west, south, east, north)

    def contains(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    @property
    def center(self) -> tuple[float, float]:
        """(lat, lon) of the box centre."""
        return (self.south + self.north) / 2, (self.west + self.east) / 2

    def as_firms(self) -> str:
        """FIRMS area API order: west,south,east,north."""
        return f"{self.west:g},{self.south:g},{self.east:g},{self.north:g}"

    def as_overpass(self) -> str:
        """Overpass order: south,west,north,east."""
        return f"{self.south:g},{self.west:g},{self.north:g},{self.east:g}"

    def as_list(self) -> list[float]:
        return [self.west, self.south, self.east, self.north]

    def tiles(self, size_deg: float) -> list["BBox"]:
        """Split into roughly size_deg x size_deg tiles (used to keep Overpass queries small)."""
        cols = max(1, math.ceil((self.east - self.west) / size_deg))
        rows = max(1, math.ceil((self.north - self.south) / size_deg))
        dx = (self.east - self.west) / cols
        dy = (self.north - self.south) / rows
        out: list[BBox] = []
        for r in range(rows):
            for c in range(cols):
                out.append(
                    BBox(
                        round(self.west + c * dx, 6),
                        round(self.south + r * dy, 6),
                        round(self.west + (c + 1) * dx, 6),
                        round(self.south + (r + 1) * dy, 6),
                    )
                )
        return out
