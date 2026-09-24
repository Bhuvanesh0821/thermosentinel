"""Response cache: repeated reads are served from memory, but any data-changing event
invalidates them immediately; progress notices do not."""

import json

from app.core import cache
from app.core.events import bus


def test_cache_hits_until_data_changes():
    calls = []

    def build():
        calls.append(1)
        return {"n": len(calls)}, {"source": "test"}

    first = cache.cached_ok("t_cache", {"a": 1}, build)
    second = cache.cached_ok("t_cache", {"a": 1}, build)
    assert first.headers["X-Cache"] == "MISS" and second.headers["X-Cache"] == "HIT"
    assert json.loads(second.body)["data"] == {"n": 1} and len(calls) == 1

    bus.publish("ingestion.facilities.progress", {})  # progress does not invalidate
    assert cache.cached_ok("t_cache", {"a": 1}, build).headers["X-Cache"] == "HIT"

    bus.publish("analysis.completed", {})  # completed work does
    fresh = cache.cached_ok("t_cache", {"a": 1}, build)
    assert fresh.headers["X-Cache"] == "MISS" and json.loads(fresh.body)["data"] == {"n": 2}


def test_parameters_are_part_of_the_key():
    a = cache.cached_ok("t_params", {"days": 7}, lambda: ({"d": 7}, None))
    b = cache.cached_ok("t_params", {"days": 14}, lambda: ({"d": 14}, None))
    assert json.loads(a.body)["data"] == {"d": 7} and json.loads(b.body)["data"] == {"d": 14}
