"""Shared test fixtures and factory helpers."""

import hashlib
import json
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lesgoski.database.engine import Base
from lesgoski.database.models import Flight, SearchProfile, Deal


@pytest.fixture
def db():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _flight_id(origin, destination, departure_time, adults):
    """Compute the same MD5 id used by FlightSchema.unique_id."""
    raw = f"{origin}_{destination}_{departure_time.isoformat()}_{adults}"
    return hashlib.md5(raw.encode()).hexdigest()


def make_flight(
    db,
    *,
    origin="PSA",
    destination="BCN",
    departure_time=None,
    arrival_time=None,
    price=29.99,
    adults=1,
    origin_full="Pisa Airport, Italy",
    destination_full="Barcelona Airport, Spain",
    flight_number="FR1234",
):
    """Create and persist a Flight with sensible defaults."""
    if departure_time is None:
        departure_time = datetime(2025, 7, 4, 18, 30)  # a Friday
    if arrival_time is None:
        from datetime import timedelta
        arrival_time = departure_time + timedelta(hours=2)

    fid = _flight_id(origin, destination, departure_time, adults)
    flight = Flight(
        id=fid,
        origin=origin,
        destination=destination,
        departure_time=departure_time,
        arrival_time=arrival_time,
        price=price,
        adults=adults,
        currency="EUR",
        flight_number=flight_number,
        origin_full=origin_full,
        destination_full=destination_full,
        updated_at=datetime.now(),
    )
    db.add(flight)
    db.flush()
    return flight


def make_profile(
    db,
    *,
    name="Weekend BCN",
    origins=None,
    adults=1,
    max_price=100.0,
    strategy_dict=None,
    allowed_destinations=None,
):
    """Create and persist a SearchProfile with a default weekend strategy."""
    if origins is None:
        origins = ["PSA"]
    if strategy_dict is None:
        strategy_dict = {
            "out_days": {"4": [17, 24]},   # Friday 17:00-24:00
            "in_days": {"6": [15, 23]},     # Sunday 15:00-23:00
            "min_nights": 2,
            "max_nights": 3,
        }

    profile = SearchProfile()
    profile.name = name
    profile.origins = origins
    profile.adults = adults
    profile.max_price = max_price
    profile._strategy_object = json.dumps(strategy_dict)
    profile.is_active = True
    if allowed_destinations:
        profile.allowed_destinations = allowed_destinations
    db.add(profile)
    db.flush()
    return profile
