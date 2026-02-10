"""Tests for services/matcher.py — deal matching logic."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from lesgoski.core.schemas import StrategyConfig
from lesgoski.database.models import Flight, Deal
from lesgoski.services.matcher import DealMatcher
from tests.conftest import make_flight, make_profile


# ---------------------------------------------------------------------------
# Helper: build a minimal Flight-like object for _is_valid_match
# ---------------------------------------------------------------------------

@dataclass
class _FlightStub:
    """Lightweight stand-in for Flight — only the fields _is_valid_match reads."""
    departure_time: datetime
    arrival_time: datetime


def _flight_stub(departure_time, arrival_time=None):
    if arrival_time is None:
        arrival_time = departure_time + timedelta(hours=2)
    return _FlightStub(departure_time=departure_time, arrival_time=arrival_time)


def _default_config(**overrides):
    defaults = dict(
        out_days={4: (17, 24)},   # Friday 17-24
        in_days={6: (15, 23)},    # Sunday 15-23
        min_nights=2,
        max_nights=3,
    )
    defaults.update(overrides)
    return StrategyConfig(**defaults)


# ---------------------------------------------------------------------------
# _is_valid_match — pure logic
# ---------------------------------------------------------------------------

class TestIsValidMatch:
    """Tests for DealMatcher._is_valid_match (no DB needed)."""

    def _matcher(self):
        """Create a DealMatcher with a dummy db (not used by _is_valid_match)."""
        m = DealMatcher.__new__(DealMatcher)
        m.db = None
        return m

    def test_correct_weekday_and_time(self, monkeypatch):
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        out = _flight_stub(datetime(2025, 7, 4, 18, 0))   # Friday 18:00
        inb = _flight_stub(datetime(2025, 7, 6, 16, 0))   # Sunday 16:00 (2 nights)
        assert self._matcher()._is_valid_match(out, inb, _default_config()) is True

    def test_wrong_outbound_weekday(self, monkeypatch):
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        out = _flight_stub(datetime(2025, 7, 3, 18, 0))   # Thursday
        inb = _flight_stub(datetime(2025, 7, 6, 16, 0))
        assert self._matcher()._is_valid_match(out, inb, _default_config()) is False

    def test_wrong_inbound_weekday(self, monkeypatch):
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        out = _flight_stub(datetime(2025, 7, 4, 18, 0))   # Friday
        inb = _flight_stub(datetime(2025, 7, 5, 16, 0))   # Saturday (not Sunday)
        # Also only 1 night, below min_nights=2
        assert self._matcher()._is_valid_match(out, inb, _default_config()) is False

    def test_time_outside_window_beyond_tolerance(self, monkeypatch):
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        # Window is 17-24, tolerance=1 → effective range is hour >= 16.
        # 15:00 is still below 16.
        out = _flight_stub(datetime(2025, 7, 4, 15, 0))
        inb = _flight_stub(datetime(2025, 7, 6, 16, 0))
        assert self._matcher()._is_valid_match(out, inb, _default_config()) is False

    def test_time_within_tolerance(self, monkeypatch):
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        # Window is 17-24, tolerance=1 → effective start is 16:00.
        out = _flight_stub(datetime(2025, 7, 4, 16, 0))
        inb = _flight_stub(datetime(2025, 7, 6, 16, 0))
        assert self._matcher()._is_valid_match(out, inb, _default_config()) is True

    def test_stay_too_short(self, monkeypatch):
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        out = _flight_stub(datetime(2025, 7, 4, 18, 0))   # Friday
        inb = _flight_stub(datetime(2025, 7, 5, 16, 0))   # Saturday — 1 night < min 2
        # Use config that accepts Saturday inbound
        cfg = _default_config(in_days={5: (15, 23)})
        assert self._matcher()._is_valid_match(out, inb, cfg) is False

    def test_stay_too_long(self, monkeypatch):
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        out = _flight_stub(datetime(2025, 7, 4, 18, 0))   # Friday
        inb = _flight_stub(datetime(2025, 7, 9, 16, 0))   # Wednesday — 5 nights > max 3
        cfg = _default_config(in_days={2: (15, 23)})       # Accept Wednesday
        assert self._matcher()._is_valid_match(out, inb, cfg) is False

    def test_empty_out_days_rejects_all(self, monkeypatch):
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        out = _flight_stub(datetime(2025, 7, 4, 18, 0))
        inb = _flight_stub(datetime(2025, 7, 6, 16, 0))
        cfg = _default_config(out_days={})
        assert self._matcher()._is_valid_match(out, inb, cfg) is False


# ---------------------------------------------------------------------------
# DealMatcher.run() — integration tests with in-memory SQLite
# ---------------------------------------------------------------------------

class TestMatcherRun:
    """Integration tests for the full matching pipeline."""

    def test_pass1_same_airport_match(self, db, monkeypatch):
        """Outbound PSA→BCN + inbound BCN→PSA should produce 1 deal."""
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        monkeypatch.setattr("lesgoski.services.matcher.NEARBY_AIRPORT_RADIUS_KM", 0)

        out = make_flight(db, origin="PSA", destination="BCN",
                          departure_time=datetime(2025, 7, 4, 18, 0), price=30)
        inb = make_flight(db, origin="BCN", destination="PSA",
                          departure_time=datetime(2025, 7, 6, 16, 0), price=30,
                          origin_full="Barcelona Airport, Spain",
                          destination_full="Pisa Airport, Italy")
        profile = make_profile(db, max_price=100)
        db.flush()

        matcher = DealMatcher(db=db)
        count = matcher.run(profile)
        assert count == 1

        deals = db.query(Deal).filter_by(profile_id=profile.id).all()
        assert len(deals) == 1
        assert deals[0].total_price_pp == 60.0

    def test_pass2_cross_airport_match(self, db, monkeypatch):
        """PSA→GRO outbound + BCN→PSA inbound should match via nearby airports."""
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        monkeypatch.setattr("lesgoski.services.matcher.NEARBY_AIRPORT_RADIUS_KM", 100)

        out = make_flight(db, origin="PSA", destination="GRO",
                          departure_time=datetime(2025, 7, 4, 18, 0), price=25,
                          destination_full="Girona Airport, Spain")
        inb = make_flight(db, origin="BCN", destination="PSA",
                          departure_time=datetime(2025, 7, 6, 16, 0), price=25,
                          origin_full="Barcelona Airport, Spain",
                          destination_full="Pisa Airport, Italy")
        profile = make_profile(db, max_price=100)
        db.flush()

        matcher = DealMatcher(db=db)
        count = matcher.run(profile)
        assert count == 1

    def test_no_duplicate_across_passes(self, db, monkeypatch):
        """A same-airport pair should not be duplicated by Pass 2."""
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        monkeypatch.setattr("lesgoski.services.matcher.NEARBY_AIRPORT_RADIUS_KM", 100)

        make_flight(db, origin="PSA", destination="BCN",
                    departure_time=datetime(2025, 7, 4, 18, 0), price=30)
        make_flight(db, origin="BCN", destination="PSA",
                    departure_time=datetime(2025, 7, 6, 16, 0), price=30,
                    origin_full="Barcelona Airport, Spain",
                    destination_full="Pisa Airport, Italy")
        profile = make_profile(db, max_price=100)
        db.flush()

        matcher = DealMatcher(db=db)
        count = matcher.run(profile)
        # Should be exactly 1, not duplicated
        assert count == 1

    def test_stale_deal_pruning(self, db, monkeypatch):
        """Deals from a previous run that no longer match should be pruned."""
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        monkeypatch.setattr("lesgoski.services.matcher.NEARBY_AIRPORT_RADIUS_KM", 0)

        out = make_flight(db, origin="PSA", destination="BCN",
                          departure_time=datetime(2025, 7, 4, 18, 0), price=30)
        inb = make_flight(db, origin="BCN", destination="PSA",
                          departure_time=datetime(2025, 7, 6, 16, 0), price=30,
                          origin_full="Barcelona Airport, Spain",
                          destination_full="Pisa Airport, Italy")
        profile = make_profile(db, max_price=100)
        db.flush()

        matcher = DealMatcher(db=db)

        # Run 1 — should create the deal
        count1 = matcher.run(profile)
        assert count1 == 1
        db.flush()

        # Now remove the inbound flight so the pair no longer matches
        db.delete(inb)
        db.flush()

        # Run 2 — should find 0 new matches and prune the stale deal
        count2 = matcher.run(profile)
        assert count2 == 0

        remaining = db.query(Deal).filter_by(profile_id=profile.id).all()
        assert len(remaining) == 0

    def test_price_over_budget_rejected(self, db, monkeypatch):
        """Flights whose combined price exceeds max_price * 1.25 should not match."""
        monkeypatch.setattr("lesgoski.services.matcher.HOUR_TOLERANCE", 1)
        monkeypatch.setattr("lesgoski.services.matcher.NEARBY_AIRPORT_RADIUS_KM", 0)

        make_flight(db, origin="PSA", destination="BCN",
                    departure_time=datetime(2025, 7, 4, 18, 0), price=80)
        make_flight(db, origin="BCN", destination="PSA",
                    departure_time=datetime(2025, 7, 6, 16, 0), price=80,
                    origin_full="Barcelona Airport, Spain",
                    destination_full="Pisa Airport, Italy")
        # max_price=100, 1.25x = 125.  80+80=160 > 125
        profile = make_profile(db, max_price=100)
        db.flush()

        matcher = DealMatcher(db=db)
        count = matcher.run(profile)
        assert count == 0
