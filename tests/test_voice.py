"""Voice / command interpreter: whitelisted intents only, and unsupported requests are never
reported as executed. Intents that read the database are covered in test_db_integration."""

import pytest

from app.voice.interpreter import EXAMPLES, interpret, normalise


class NoDb:
    """Any database access in these tests is a bug: the intents below are pure routing."""

    def execute(self, *a, **k):  # pragma: no cover - fails the test if reached
        raise AssertionError("unexpected database access")


def run(cmd):
    return interpret(cmd, NoDb())


def test_normalise_strips_politeness_and_punctuation():
    assert normalise("  Hey ThermoSentinel, could you SHOW alerts?! ") == "show alerts"


def test_high_priority_industrial_incidents():
    r = run("Show high priority industrial incidents")
    assert r.supported and r.intent == "show_incidents"
    path = r.action["path"]
    assert path.startswith("/incidents?") and "min_priority=high" in path and "classification=" in path
    assert "gas_flare_like" in path and "persistent_unattributed_source" not in path


@pytest.mark.parametrize(
    "cmd,ftype",
    [
        ("Show incidents near power plants", "thermal_power_plant"),
        ("show incidents near refineries", "refinery"),
        ("incidents near steel plants", "steel_plant"),
        ("show incidents at coal mines", "mining"),
    ],
)
def test_incidents_near_facility_type(cmd, ftype):
    r = run(cmd)
    assert r.intent == "show_incidents"
    assert f"facility_type={ftype}" in r.action["path"]
    assert "near" in r.interpreted_as


def test_navigation():
    assert run("open analytics").action == {"type": "navigate", "path": "/analytics"}
    assert run("go to the alerts page").action["path"] == "/alerts"
    assert run("show thermal sources").action["path"] == "/thermal-sources"


def test_show_facilities_of_a_type():
    r = run("show refineries")
    assert r.intent == "show_facilities" and r.action["path"] == "/facilities?type=refinery"


def test_help_lists_examples():
    r = run("what can you do")
    assert r.supported and r.suggestions == EXAMPLES


@pytest.mark.parametrize("cmd", ["delete all incidents", "drop table alerts", "send an email to the minister", "", "   "])
def test_unsupported_requests_are_not_executed(cmd):
    r = run(cmd)
    assert r.supported is False
    assert r.action is None
    assert r.suggestions
