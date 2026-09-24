"""Persistence categories never overstate what the stored history supports."""

import pytest

from app.analytics.persistence import classify_persistence

KW = dict(radius_m=1000, min_days_persistent=5, min_coverage_days=5, min_ratio=0.25)


@pytest.mark.parametrize(
    "detection_days, coverage_days, expected",
    [
        (7, 7, "persistent"),
        (10, 30, "persistent"),
        (5, 30, "recurring"),  # 5/30 < 25%: repeated but not persistent
        (3, 7, "recurring"),
        (1, 2, "insufficient_history"),  # too little history to judge
        (1, 10, "transient"),
    ],
)
def test_categories(detection_days, coverage_days, expected):
    assert classify_persistence(detection_days, coverage_days, **KW).category == expected


def test_never_persistent_without_enough_coverage():
    # 4 of 4 days is 100% but below the minimum coverage and minimum days.
    assert classify_persistence(4, 4, **KW).category == "recurring"


def test_coverage_is_at_least_detection_days():
    result = classify_persistence(6, 3, **KW)
    assert result.coverage_days == 6 and result.ratio == 1.0
