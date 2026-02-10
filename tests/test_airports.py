"""Tests for services/airports.py — haversine distance and metro-area grouping."""

import pytest
from lesgoski.services.airports import (
    _haversine_km,
    get_nearby_airports,
    get_nearby_set,
    are_nearby,
)


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

def test_haversine_same_point():
    assert _haversine_km(41.0, 2.0, 41.0, 2.0) == 0.0


def test_haversine_bcn_gro():
    """BCN ↔ GRO is roughly 80-95 km."""
    dist = _haversine_km(41.2971, 2.07846, 41.904639, 2.761774)
    assert 75 <= dist <= 100


def test_haversine_bcn_psa():
    """BCN ↔ PSA is roughly 800 km — far apart."""
    dist = _haversine_km(41.2971, 2.07846, 43.6839, 10.3927)
    assert 700 <= dist <= 900


def test_haversine_antipodal():
    """Opposite sides of the globe ≈ 20015 km (half circumference)."""
    dist = _haversine_km(0, 0, 0, 180)
    assert 20000 <= dist <= 20100


# ---------------------------------------------------------------------------
# get_nearby_airports
# ---------------------------------------------------------------------------

def test_nearby_includes_self():
    result = get_nearby_airports("BCN", radius_km=100)
    assert "BCN" in result


def test_nearby_finds_gro_from_bcn():
    """GRO is ~85 km from BCN — should appear within 100 km radius."""
    result = get_nearby_airports("BCN", radius_km=100)
    assert "GRO" in result


def test_nearby_radius_zero_returns_only_self():
    result = get_nearby_airports("BCN", radius_km=0)
    assert result == ["BCN"]


def test_nearby_negative_radius_returns_only_self():
    result = get_nearby_airports("BCN", radius_km=-1)
    assert result == ["BCN"]


def test_nearby_unknown_iata():
    """Unknown airport code should return just itself."""
    result = get_nearby_airports("ZZZ", radius_km=100)
    assert result == ["ZZZ"]


# ---------------------------------------------------------------------------
# are_nearby
# ---------------------------------------------------------------------------

def test_are_nearby_self():
    assert are_nearby("BCN", "BCN") is True


def test_are_nearby_bcn_gro():
    assert are_nearby("BCN", "GRO", radius_km=100) is True


def test_are_nearby_symmetric():
    """Nearness must be symmetric."""
    assert are_nearby("BCN", "GRO", radius_km=100) is True
    assert are_nearby("GRO", "BCN", radius_km=100) is True


def test_are_nearby_far_apart():
    """BCN and PSA are ~800 km apart — not nearby at 100 km."""
    assert are_nearby("BCN", "PSA", radius_km=100) is False
