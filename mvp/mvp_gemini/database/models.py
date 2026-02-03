# database/models.py
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.db import Base
from core.schemas import StrategyConfig
import json


class Flight(Base):
    """
    ATOMIC UNIT: Represents a single one-way flight.
    Round trips are just two of these combined.
    """
    __tablename__ = 'flights'

    id = Column(String, primary_key=True) # Hash: carrier_flightnum_date
    origin = Column(String, index=True)
    destination = Column(String, index=True)
    departure_time = Column(DateTime, index=True)
    arrival_time = Column(DateTime)
    flight_number = Column(String)
    price = Column(Float)
    currency = Column(String, default="EUR")
    
    # Metadata
    last_seen = Column(DateTime, default=func.now())
    source_api = Column(String) # e.g. "ryanair"

    # Index for fast matching: Give me flights from A to B on specific dates
    __table_args__ = (
        Index('idx_route_date', 'origin', 'destination', 'departure_time'),
    )


class SearchProfile(Base):
    """
    USER CONFIGURATION: Replaces your static config lists.
    """
    __tablename__ = 'search_profiles'

    id = Column(Integer, primary_key=True)
    name = Column(String) # e.g., "Weekend Escape"
    
    # Constraints
    _origins = Column("origins", String)
    allowed_destinations = Column(String, nullable=True) # JSON list or null for "Any"
    max_price = Column(Float)
    
    # Strategy Definition (JSON blob or separate columns)
    # Storing as JSON for flexibility in early stages is often better than over-normalizing
    strategy_config = Column(String)
    is_active = Column(Boolean, default=True)
    
    @property
    def origins(self) -> list[str]:
        """Returns python list: ['PSA', 'BLQ']"""
        if not self._origins:
            return []
        return json.loads(self._origins)

    @origins.setter
    def origins(self, value: list[str]):
        """Saves python list as JSON string"""
        self._origins = json.dumps(value)
    
    @property
    def strategy_object(self) -> StrategyConfig:
        """Parses the JSON string into a Pydantic object"""
        if not self.strategy_config:
            return None
        return StrategyConfig.model_validate_json(self.strategy_config)

    @strategy_object.setter
    def strategy_object(self, config: StrategyConfig):
        """Dumps Pydantic object back to JSON string"""
        self.strategy_config = config.model_dump_json()


class Deal(Base):
    """
    DETECTED MATCH: The result of the Matcher service.
    """
    __tablename__ = 'deals'

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey('search_profiles.id'))
    
    # Link to the atomic flights
    outbound_flight_id = Column(String, ForeignKey('flights.id'))
    inbound_flight_id = Column(String, ForeignKey('flights.id'))
    
    total_price = Column(Float)
    found_at = Column(DateTime, default=func.now())
    notified = Column(Boolean, default=False)

    outbound = relationship("Flight", foreign_keys=[outbound_flight_id])
    inbound = relationship("Flight", foreign_keys=[inbound_flight_id])
