"""India monitoring area: official-claim boundary + EEZ."""

import pytest

from app.geo.boundary import get_monitoring_area


@pytest.mark.parametrize(
    "label, lat, lon, inside",
    [
        ("New Delhi", 28.614, 77.209, True),
        ("Aksai Chin (claimed by India)", 35.2, 79.5, True),
        ("Gilgit (claimed by India)", 35.92, 74.31, True),
        ("Tawang, Arunachal Pradesh", 27.59, 91.86, True),
        ("Port Blair, Andaman & Nicobar", 11.62, 92.73, True),
        ("Mumbai High offshore field (EEZ)", 19.4, 71.3, True),
        ("Lahore, Pakistan", 31.55, 74.35, False),
        ("Kathmandu, Nepal", 27.71, 85.32, False),
        ("Dhaka, Bangladesh", 23.81, 90.41, False),
        ("Colombo, Sri Lanka", 6.93, 79.86, False),
        ("Bangkok, Thailand", 13.75, 100.5, False),
    ],
)
def test_monitoring_area_membership(label, lat, lon, inside):
    assert get_monitoring_area().contains(lat, lon) is inside, label


def test_land_excludes_offshore_but_area_includes_it():
    area = get_monitoring_area()
    assert not area.land.covers(__import__("shapely.geometry", fromlist=["Point"]).Point(71.3, 19.4))
    assert area.contains(19.4, 71.3)


def test_bbox_derived_from_boundary():
    bbox = get_monitoring_area().bbox
    assert 65 < bbox.west < 67 and 3 < bbox.south < 5 and 97 < bbox.east < 98 and 36.5 < bbox.north < 37.5


def test_display_geojson_has_mask_and_lines():
    fc = get_monitoring_area().display_geojson()
    assert [f["properties"]["role"] for f in fc["features"]] == ["mask", "monitoring_area", "land"]
    assert fc["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}
