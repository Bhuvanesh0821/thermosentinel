"""Great-circle distance helpers (vectorised with NumPy)."""

from __future__ import annotations

import numpy as np

EARTH_RADIUS_KM = 6371.0088  # IUGG mean Earth radius


def haversine_km(lat1, lon1, lat2, lon2):
    """Haversine distance in km. Accepts scalars or NumPy arrays (broadcast)."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
