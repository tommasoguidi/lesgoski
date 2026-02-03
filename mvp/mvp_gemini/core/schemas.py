# core/schemas.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import List
from typing import Dict, Tuple


class FlightSchema(BaseModel):
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    flight_number: str
    price: float
    currency: str = "EUR"

    @property
    def unique_id(self) -> str:
        # Deterministic ID generation
        import hashlib
        raw = f"{self.flight_number}_{self.departure_time.isoformat()}"
        return hashlib.md5(raw.encode()).hexdigest()


class DateRange(BaseModel):
    start: datetime
    end: datetime


class ScanTask(BaseModel):
    """Instructions for the scanner"""
    origins: List[str]
    date_range: DateRange


TimeWindow = Tuple[int, int]

class StrategyConfig(BaseModel):
    # Maps Day of Week (int) -> Time Window
    # Example: {4: (17, 24)} means Friday 17:00 to 24:00
    out_days: Dict[int, TimeWindow]
    in_days: Dict[int, TimeWindow]
    
    min_stay: int = Field(..., ge=0) # Must be >= 0
    max_stay: int = Field(..., ge=0)

    @field_validator('out_days', 'in_days', mode='before')
    @classmethod
    def parse_keys_to_int(cls, v):
        """
        Automatically converts JSON string keys "4" back to integer 4.
        mode='before' runs this BEFORE Pydantic tries to validate the types.
        """
        if isinstance(v, dict):
            # Convert keys to int, leave values as is
            return {int(k): val for k, val in v.items()}
        return v
