# core/schemas.py
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
import hashlib
from typing import List
from typing import Dict, Tuple


class FlightSchema(BaseModel):
    departure_time: datetime
    arrival_time: datetime
    flight_number: str
    price: float
    currency: str = "EUR"
    origin: str
    origin_full: str
    destination: str
    destination_full: str
    adults: int = 1

    @property
    def unique_id(self) -> str:
        raw = f"{self.origin}_{self.destination}_{self.departure_time.isoformat()}_{self.adults}"
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

    min_nights: int = Field(..., ge=0)
    max_nights: int = Field(..., ge=0)

    @field_validator('out_days', 'in_days', mode='before')
    @classmethod
    def parse_keys_to_int(cls, v):
        """
        Automatically converts JSON string keys "4" back to integer 4.
        mode='before' runs this BEFORE Pydantic tries to validate the types.
        """
        if isinstance(v, dict):
            out = {}
            for k, val in v.items():
                try:
                    out[int(k)] = val
                except (TypeError, ValueError):
                    raise ValueError(f"Invalid day key: {k!r}")
            return out
        return v

    @field_validator('out_days', 'in_days')
    @classmethod
    def validate_day_range(cls, v):
        for day in v:
            if not 0 <= day <= 6:
                raise ValueError(f"Invalid weekday: {day}")
        return v

    @model_validator(mode='after')
    def check_stay_bounds(self):
        if self.min_nights > self.max_nights:
            raise ValueError("min_nights cannot be greater than max_nights")
        return self
