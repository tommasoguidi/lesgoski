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
    
    # columns
    id = Column(String, primary_key=True) # Hash: carrier_flightnum_date
    profile_id = Column(Integer, ForeignKey('search_profiles.id'))
    source_api = Column(String) # e.g. "ryanair"
    updated_at = Column(DateTime, default=func.now())
    # flight schema fields
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
    )
    
    # relationships
    profile = relationship("SearchProfile", foreign_keys=[profile_id])


class SearchProfile(Base):
    """
    USER CONFIGURATION: Replaces your static config lists.
    """
    __tablename__ = 'search_profiles'
    
    # columns
    id = Column(Integer, primary_key=True)
    name = Column(String) # e.g., "Weekend Escape"
    _origins = Column("origins", String)
    adults = Column(Integer, default=1)
    allowed_destinations = Column(String, nullable=True)
    max_price = Column(Float)
    _strategy_object = Column(String)
    is_active = Column(Boolean, default=True)
    lookup_horizon = Column(Integer, default=60) # Days into the future to scan
    updated_at = Column(DateTime, default=func.now())
    update_interval_hours = Column(Integer, default=12)
    
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
    """
    __tablename__ = 'deals'
    
    # columns
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey('search_profiles.id'))
    outbound_flight_id = Column(String, ForeignKey('flights.id'))
    inbound_flight_id = Column(String, ForeignKey('flights.id'))
    total_price_pp= Column(Float)   # lo divido per adulti
    updated_at = Column(DateTime, default=func.now())
    notified = Column(Boolean, default=False)
    
    # relationships
    outbound = relationship("Flight", foreign_keys=[outbound_flight_id])
    inbound = relationship("Flight", foreign_keys=[inbound_flight_id])
    profile = relationship("SearchProfile", foreign_keys=[profile_id])
