"""Tests for webapp/utils.py — country code matching and booking URLs."""

from datetime import datetime

import pytest

from lesgoski.webapp.utils import get_country_code, get_booking_links
from lesgoski.database.models import Deal, Flight, SearchProfile
from tests.conftest import make_flight, make_profile


# ---------------------------------------------------------------------------
# get_country_code
# ---------------------------------------------------------------------------

def test_country_code_exact_spain():
    assert get_country_code("Barcelona Airport, Spain") == "ES"


def test_country_code_exact_italy():
    assert get_country_code("Pisa Airport, Italy") == "IT"


def test_country_code_fuzzy_match():
    """'Czech Republic' should fuzzy-match to CZ."""
    result = get_country_code("Prague Airport, Czech Republic")
    assert result == "CZ"


def test_country_code_single_word():
    """Just a country name with no comma."""
    assert get_country_code("Italy") == "IT"


def test_country_code_empty_string():
    assert get_country_code("") == "EU"


def test_country_code_unknown():
    assert get_country_code("Somewhere, Neverland") == "EU"


# ---------------------------------------------------------------------------
# get_booking_links
# ---------------------------------------------------------------------------

def _make_deal_in_db(db, *, out_dest="BCN", in_origin="BCN"):
    """Create a complete Deal with related flights and profile in the test DB."""
    out = make_flight(
        db, origin="PSA", destination=out_dest,
        departure_time=datetime(2025, 7, 4, 18, 0), price=30,
        destination_full=f"{out_dest} Airport, Spain",
    )
    inb = make_flight(
        db, origin=in_origin, destination="PSA",
        departure_time=datetime(2025, 7, 6, 16, 0), price=30,
        origin_full=f"{in_origin} Airport, Spain",
        destination_full="Pisa Airport, Italy",
    )
    profile = make_profile(db)

    deal = Deal(
        profile_id=profile.id,
        outbound_flight_id=out.id,
        inbound_flight_id=inb.id,
        total_price_pp=60.0,
        updated_at=datetime.now(),
        notified=False,
    )
    db.add(deal)
    db.flush()

    # Eagerly load relationships so they're available outside the session context
    deal.outbound = out
    deal.inbound = inb
    deal.profile = profile
    return deal


def test_booking_links_standard_round_trip(db):
    """Same airports → single 'Book Now' button with isReturn=true."""
    deal = _make_deal_in_db(db, out_dest="BCN", in_origin="BCN")
    links = get_booking_links(deal)

    assert len(links) == 1
    assert links[0]["label"] == "Book Now"
    assert "isReturn=true" in links[0]["url"]
    assert "dateOut=2025-07-04" in links[0]["url"]
    assert "dateIn=2025-07-06" in links[0]["url"]


def test_booking_links_cross_airport(db):
    """Different airports → two buttons (outbound + return), each one-way."""
    deal = _make_deal_in_db(db, out_dest="GRO", in_origin="BCN")
    links = get_booking_links(deal)

    assert len(links) == 2
    assert links[0]["label"] == "Book Outbound"
    assert links[1]["label"] == "Book Return"
    assert "isReturn=false" in links[0]["url"]
    assert "isReturn=false" in links[1]["url"]
