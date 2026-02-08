# database/models.py
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from lesgoski.database.engine import Base
from lesgoski.core.schemas import StrategyConfig
import json


class ScanLog(Base):
    """
    Tracks when each (origin, adults) pair was last scanned.
    Used to avoid duplicate API calls across profiles.
    """
    __tablename__ = 'scan_log'

    id = Column(Integer, primary_key=True)
    origin = Column(String, nullable=False, index=True)
    adults = Column(Integer, nullable=False)
    scanned_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        Index('idx_scan_dedup', 'origin', 'adults'),
    )


class Flight(Base):
    """
    ATOMIC UNIT: Represents a single one-way flight.
    Profile-independent — shared across all profiles with the same adults count.
    ID encodes (origin, destination, departure_time, adults).
    """
    __tablename__ = 'flights'

    id = Column(String, primary_key=True)
    source_api = Column(String, default="ryanair")
    updated_at = Column(DateTime, default=func.now())
    departure_time = Column(DateTime, index=True)
    arrival_time = Column(DateTime)
    flight_number = Column(String)
    price = Column(Float)
    currency = Column(String, default="EUR")
    origin = Column(String, index=True)
    origin_full = Column(String)
    destination = Column(String, index=True)
    destination_full = Column(String)
    adults = Column(Integer, default=1)

    __table_args__ = (
        Index('idx_route_date', 'origin', 'destination', 'departure_time'),
        Index('idx_origin_adults', 'origin', 'adults'),
    )


class SearchProfile(Base):
    """
    USER CONFIGURATION: Defines what flights to match and how.
    Scanning parameters (origins, adults) are here but shared via ScanLog dedup.
    Backend-only globals control horizon and update interval.
    """
    __tablename__ = 'search_profiles'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    _origins = Column("origins", String)
    adults = Column(Integer, default=1)
    _allowed_destinations = Column("allowed_destinations", String, nullable=True)
    max_price = Column(Float)
    _strategy_object = Column(String)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=func.now())
    _notify_destinations = Column("notify_destinations", String, nullable=True)

    @property
    def origins(self) -> list[str]:
        """Returns python list: ['PSA', 'BLQ']"""
        if not self._origins:
            return []
        return json.loads(self._origins)

    @origins.setter
    def origins(self, value: list[str]):
        self._origins = json.dumps(value)

    @property
    def allowed_destinations(self) -> list[str]:
        if not self._allowed_destinations:
            return []
        return json.loads(self._allowed_destinations)

    @allowed_destinations.setter
    def allowed_destinations(self, value: list[str]):
        self._allowed_destinations = json.dumps(value) if value else None

    @property
    def notify_destinations(self) -> list[str]:
        """IATA codes of destinations with immediate notifications enabled (bell toggle)."""
        if not self._notify_destinations:
            return []
        return json.loads(self._notify_destinations)

    @notify_destinations.setter
    def notify_destinations(self, value: list[str]):
        self._notify_destinations = json.dumps(value) if value else None

    @property
    def strategy_object(self) -> StrategyConfig:
        """Parses the JSON string into a Pydantic object"""
        if not self._strategy_object:
            return None
        return StrategyConfig.model_validate_json(self._strategy_object)

    @strategy_object.setter
    def strategy_object(self, config: StrategyConfig):
        """Dumps Pydantic object back to JSON string"""
        self._strategy_object = config.model_dump_json()


class Deal(Base):
    """
    DETECTED MATCH: The result of the Matcher service.
    Profile-specific, references shared flights via simple FK.
    """
    __tablename__ = 'deals'

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey('search_profiles.id'))
    outbound_flight_id = Column(String, ForeignKey('flights.id'))
    inbound_flight_id = Column(String, ForeignKey('flights.id'))
    total_price_pp = Column(Float)
    updated_at = Column(DateTime, default=func.now())
    notified = Column(Boolean, default=False)

    outbound = relationship(
        "Flight",
        foreign_keys=[outbound_flight_id],
        uselist=False,
        viewonly=True,
    )
    inbound = relationship(
        "Flight",
        foreign_keys=[inbound_flight_id],
        uselist=False,
        viewonly=True,
    )
    profile = relationship("SearchProfile", foreign_keys=[profile_id])
