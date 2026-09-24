"""Map raw OSM tags to ThermoSentinel facility types.

Rules are ordered from most to least specific; the first match wins. Tags are preserved
verbatim in the database so any classification can be audited against the source.
"""

from __future__ import annotations

import re

FACILITY_TYPES: dict[str, str] = {
    "gas_flare": "Gas flare stack",
    "lng_terminal": "LNG facility",
    "refinery": "Oil refinery",
    "petrochemical": "Petrochemical complex",
    "oil_gas_facility": "Oil & gas facility",
    "chemical_plant": "Chemical / fertiliser plant",
    "steel_plant": "Iron & steel plant",
    "metal_smelter": "Metal smelter / foundry",
    "thermal_power_plant": "Thermal power plant",
    "cement_plant": "Cement plant",
    "brick_kiln": "Brick kiln / kiln",
    "mining": "Mining area",
    "industrial_works": "Industrial works",
}

# Relative plausibility that a satellite thermal anomaly originates from the facility's
# own processes (flaring, furnaces, stacks). Used by the intelligence engine; documented
# in docs/intelligence-methodology.md.
THERMAL_RELEVANCE: dict[str, float] = {
    "gas_flare": 1.0,
    "refinery": 1.0,
    "steel_plant": 1.0,
    "lng_terminal": 0.9,
    "oil_gas_facility": 0.9,
    "metal_smelter": 0.9,
    "petrochemical": 0.85,
    "thermal_power_plant": 0.8,
    "chemical_plant": 0.7,
    "cement_plant": 0.7,
    "brick_kiln": 0.6,
    "mining": 0.6,
    "industrial_works": 0.4,
}


NON_THERMAL_SOURCES = {"solar", "wind", "hydro", "tidal", "wave", "geothermal", "nuclear", "battery"}
COMBUSTION_SOURCES = re.compile(r"coal|gas|oil|diesel|biomass|biofuel|waste|lignite|biogas|bagasse", re.IGNORECASE)
THERMAL_PLANT_NAME = re.compile(r"thermal|\bTPS\b|\bSTPS\b|\bCPP\b|coal|gas|biomass|co-?generation|captive", re.IGNORECASE)
RELEVANT_PRODUCT = re.compile(
    r"steel|iron|cement|chemical|petro|oil|gas|coke|fertili|alumin|copper|zinc|glass|brick|lng|refin", re.IGNORECASE
)
RELEVANT_RESOURCE = re.compile(r"coal|lignite|iron|bauxite|manganese|copper|chromite|limestone", re.IGNORECASE)


def is_thermally_relevant(tags: dict) -> bool:
    """Local filter applied to broad Overpass results (keeps the remote query cheap)."""
    if (tags.get("power") or "") == "plant":
        sources = {s.strip().lower() for s in (tags.get("plant:source") or "").split(";") if s.strip()}
        if sources and sources <= NON_THERMAL_SOURCES:
            return False
        if any(COMBUSTION_SOURCES.search(s) for s in sources):
            return True
        if (tags.get("plant:method") or "").lower() == "combustion":
            return True
        return bool(THERMAL_PLANT_NAME.search(tags.get("name") or tags.get("name:en") or ""))
    if (tags.get("man_made") or "") == "works" and not tags.get("industrial"):
        return bool(RELEVANT_PRODUCT.search(tags.get("product") or ""))
    if (tags.get("landuse") or "") == "quarry" and not tags.get("industrial"):
        return bool(RELEVANT_RESOURCE.search(tags.get("resource") or ""))
    return True


def _t(tags: dict, key: str) -> str:
    return (tags.get(key) or "").strip().lower()


def _any(pattern: str, *values: str) -> bool:
    rx = re.compile(pattern, re.IGNORECASE)
    return any(v and rx.search(v) for v in values)


def classify_facility(tags: dict) -> tuple[str, str | None]:
    """Return (facility_type, facility_subtype)."""
    industrial = _t(tags, "industrial")
    man_made = _t(tags, "man_made")
    product = _t(tags, "product")
    name = _t(tags, "name") or _t(tags, "name:en")
    power = _t(tags, "power")
    source = _t(tags, "plant:source")

    if man_made == "flare":
        return "gas_flare", None
    if _any(r"\b(sugar|edible|soya|vegetable|palm|salt|rice)\b", name, product) and industrial != "refinery":
        # e.g. "... Edible Oil Refinery" / "Sugar Refinery": food processing, not petroleum.
        return "industrial_works", "food_processing"
    if industrial == "lng" or _any(r"\blng\b|liquefied natural gas", name, product):
        return "lng_terminal", None
    if industrial == "refinery" or _any(r"refiner", name, product):
        return "refinery", None
    if industrial == "petrochemical" or _any(r"petro ?chem", name, product):
        return "petrochemical", None
    if man_made == "offshore_platform":
        return "oil_gas_facility", "offshore_platform"
    if industrial in {"oil", "gas", "gas_processing", "petroleum_terminal"}:
        return "oil_gas_facility", industrial
    if industrial in {"chemical", "fertilizer", "fertiliser"} or _any(r"chemical|fertili", product):
        return "chemical_plant", industrial or None
    if industrial in {"steelmaker", "steel", "steel_mill", "iron", "ironworks", "metallurgy", "coking", "coke", "coking_plant"} or _any(
        r"steel|iron|coke", product
    ):
        return "steel_plant", industrial or product or None
    if industrial in {"smelter", "smelting", "aluminium_smelting", "foundry"} or _any(r"alumin|copper|zinc", product):
        return "metal_smelter", industrial or product or None
    if power == "plant":
        fuel = source.split(";")[0] if source else None
        return "thermal_power_plant", fuel
    if industrial == "cement" or _any(r"cement", product, name):
        return "cement_plant", None
    if industrial == "brickyard" or man_made == "kiln" or _any(r"brick", product):
        return "brick_kiln", None
    if industrial in {"mine", "coal"} or _t(tags, "landuse") == "quarry":
        return "mining", _t(tags, "resource") or None
    if industrial == "glass" or _any(r"glass", product):
        return "industrial_works", "glass"
    if _any(r"steel", name):
        return "steel_plant", None
    if _any(r"thermal power|smelter", name):
        return ("thermal_power_plant", None) if "thermal" in name else ("metal_smelter", None)
    return "industrial_works", industrial or man_made or None
