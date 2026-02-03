from dataclasses import dataclass
from datetime import datetime
import hashlib

@dataclass
class Flight:
    departureTime: datetime
    arrivalTime: datetime
    flightNumber: str
    price: float
    currency: str
    origin: str
    originFull: str
    destination: str
    destinationFull: str

@dataclass
class Trip:
    totalPrice: float
    outbound: Flight
    inbound: Flight

    @property
    def id(self) -> str:
        """
        Genera un hash unico basato su:
        NumVoloAndata + DataOraAndata + NumVoloRitorno + DataOraRitorno
        """
        raw_string = (
            f"{self.outbound.flightNumber}_{self.outbound.departureTime.isoformat()}_"
            f"{self.inbound.flightNumber}_{self.inbound.departureTime.isoformat()}"
        )
        return hashlib.md5(raw_string.encode('utf-8')).hexdigest()
