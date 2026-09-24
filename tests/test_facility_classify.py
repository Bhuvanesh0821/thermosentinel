"""OSM tag -> facility type mapping and thermal-relevance filtering."""

import pytest

from app.ingestion.facilities.classify import classify_facility, is_thermally_relevant


@pytest.mark.parametrize(
    "tags, expected",
    [
        ({"man_made": "flare"}, "gas_flare"),
        ({"industrial": "refinery", "name": "Reliance Refinery"}, "refinery"),
        ({"man_made": "offshore_platform"}, "oil_gas_facility"),
        ({"power": "plant", "plant:source": "coal"}, "thermal_power_plant"),
        ({"landuse": "industrial", "name": "Bokaro Thermal Power Station"}, "thermal_power_plant"),
        ({"industrial": "steelmaker"}, "steel_plant"),
        ({"landuse": "industrial", "name": "Jindal Steel Works"}, "steel_plant"),
        ({"industrial": "aluminium_smelting"}, "metal_smelter"),
        ({"man_made": "kiln"}, "brick_kiln"),
        ({"landuse": "quarry", "resource": "coal"}, "mining"),
        ({"industrial": "cement"}, "cement_plant"),
        ({"landuse": "industrial", "name": "Shree Edible Oil Refinery"}, "industrial_works"),
    ],
)
def test_classification(tags, expected):
    assert classify_facility(tags)[0] == expected


@pytest.mark.parametrize(
    "tags, relevant",
    [
        ({"power": "plant", "plant:source": "solar"}, False),
        ({"power": "plant", "plant:source": "wind;solar"}, False),
        ({"power": "plant", "plant:source": "hydro"}, False),
        ({"power": "plant", "plant:source": "coal"}, True),
        ({"power": "plant", "name": "Talcher Super Thermal Power Station"}, True),
        ({"power": "plant", "name": "Unnamed plant"}, False),
        ({"man_made": "works", "product": "textiles"}, False),
        ({"man_made": "works", "product": "steel"}, True),
        ({"landuse": "quarry", "resource": "sand"}, False),
    ],
)
def test_relevance_filter(tags, relevant):
    assert is_thermally_relevant(tags) is relevant
