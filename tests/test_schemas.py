"""Tests for core/schemas.py — Pydantic validation models."""

import hashlib
from datetime import datetime

import pytest
from pydantic import ValidationError

from lesgoski.core.schemas import FlightSchema, StrategyConfig


# ---------------------------------------------------------------------------
# FlightSchema.unique_id
# ---------------------------------------------------------------------------

def _make_flight_schema(**overrides):
    defaults = dict(
        departure_time=datetime(2025, 7, 4, 18, 30),
        arrival_time=datetime(2025, 7, 4, 20, 30),
        flight_number="FR1234",
        price=29.99,
        currency="EUR",
        origin="PSA",
        origin_full="Pisa Airport, Italy",
        destination="BCN",
        destination_full="Barcelona Airport, Spain",
        adults=1,
    )
    defaults.update(overrides)
    return FlightSchema(**defaults)


def test_flight_unique_id_deterministic():
    """Two identical FlightSchemas must produce the same unique_id."""
    a = _make_flight_schema()
    b = _make_flight_schema()
    assert a.unique_id == b.unique_id


def test_flight_unique_id_matches_expected_hash():
    """The id must equal MD5(origin_destination_departure_adults)."""
    fs = _make_flight_schema()
    raw = f"PSA_BCN_2025-07-04T18:30:00_1"
    expected = hashlib.md5(raw.encode()).hexdigest()
    assert fs.unique_id == expected


def test_flight_unique_id_differs_by_origin():
    a = _make_flight_schema(origin="PSA")
    b = _make_flight_schema(origin="BLQ")
    assert a.unique_id != b.unique_id


def test_flight_unique_id_differs_by_destination():
    a = _make_flight_schema(destination="BCN")
    b = _make_flight_schema(destination="GRO")
    assert a.unique_id != b.unique_id


def test_flight_unique_id_differs_by_departure_time():
    a = _make_flight_schema(departure_time=datetime(2025, 7, 4, 18, 30))
    b = _make_flight_schema(departure_time=datetime(2025, 7, 5, 18, 30))
    assert a.unique_id != b.unique_id


def test_flight_unique_id_differs_by_adults():
    a = _make_flight_schema(adults=1)
    b = _make_flight_schema(adults=2)
    assert a.unique_id != b.unique_id


# ---------------------------------------------------------------------------
# StrategyConfig validators
# ---------------------------------------------------------------------------

def test_parse_keys_to_int():
    """String keys from JSON ("4") must be converted to int (4)."""
    cfg = StrategyConfig(
        out_days={"4": [17, 24]},
        in_days={"6": [15, 23]},
        min_nights=2,
        max_nights=3,
    )
    assert 4 in cfg.out_days
    assert 6 in cfg.in_days
    # String key should not remain
    assert "4" not in cfg.out_days
    assert "6" not in cfg.in_days


def test_validate_day_range_all_valid():
    """All weekdays 0-6 should be accepted."""
    days = {i: [0, 24] for i in range(7)}
    cfg = StrategyConfig(out_days=days, in_days={}, min_nights=0, max_nights=0)
    assert len(cfg.out_days) == 7


def test_validate_day_range_invalid_key():
    """Day key 7 (or higher) must be rejected."""
    with pytest.raises(ValidationError):
        StrategyConfig(
            out_days={7: [0, 24]},
            in_days={},
            min_nights=0,
            max_nights=0,
        )


def test_validate_day_range_negative_key():
    """Negative day key must be rejected."""
    with pytest.raises(ValidationError):
        StrategyConfig(
            out_days={-1: [0, 24]},
            in_days={},
            min_nights=0,
            max_nights=0,
        )


def test_check_stay_bounds_valid():
    cfg = StrategyConfig(
        out_days={}, in_days={}, min_nights=2, max_nights=4
    )
    assert cfg.min_nights == 2
    assert cfg.max_nights == 4


def test_check_stay_bounds_equal():
    """min == max is valid (exact stay duration)."""
    cfg = StrategyConfig(
        out_days={}, in_days={}, min_nights=3, max_nights=3
    )
    assert cfg.min_nights == cfg.max_nights == 3


def test_check_stay_bounds_invalid():
    """min_nights > max_nights must be rejected."""
    with pytest.raises(ValidationError):
        StrategyConfig(
            out_days={}, in_days={}, min_nights=5, max_nights=2
        )


def test_empty_out_days_allowed():
    """Empty out_days is valid at the schema level (UI bug was in JS, not here)."""
    cfg = StrategyConfig(
        out_days={},
        in_days={4: [17, 24]},
        min_nights=2,
        max_nights=3,
    )
    assert cfg.out_days == {}


def test_empty_in_days_allowed():
    """Same for empty in_days."""
    cfg = StrategyConfig(
        out_days={4: [17, 24]},
        in_days={},
        min_nights=2,
        max_nights=3,
    )
    assert cfg.in_days == {}
