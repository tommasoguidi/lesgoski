# services/scanner.py
from datetime import datetime, timedelta
from ryanair import Ryanair # Your existing lib
from core.schemas import FlightSchema
from database.db import SessionLocal
from database.models import Flight

class FlightScanner:
    def __init__(self):
        self.api = Ryanair(currency="EUR")
        self.db = SessionLocal()

    def run(self, origins: list[str], days_horizon: int = 60) -> int:
        """
        Dumb-scan: Just get all flights from origins for X days.
        Returns total number of flights found.
        """
        today = datetime.now().date()
        date_from = today
        date_to = today + timedelta(days=days_horizon)
        total_results = 0
        
        for origin in origins:
            print(f"Scanning from {origin}...")
            
            # 1. Scan One-Way Outbound (Origin -> Anywhere)
            # Note: Ryanair API requires a destination usually, or specialized "farefinder"
            # If using "farefinder" API (get_cheapest_flights), we can often leave dest empty
            raw_flights = self.api.get_cheapest_flights(
                airport=origin,
                date_from=date_from,
                date_to=date_to
            )
            self._bulk_upsert(raw_flights)
            total_results += len(raw_flights)

            # 2. To build Round Trips, we ideally need the return legs.
            # In a "hub" model (PSA -> X), we need to scan X -> PSA.
            # Since we don't know X yet, we extract distinct destinations from step 1
            destinations = {f.destination for f in raw_flights}
            
            for dest in destinations:
                # Scan One-Way Inbound (Anywhere -> Origin)
                raw_inbound = self.api.get_cheapest_flights(
                    airport=dest,
                    destination_airport=origin, # Explicitly back to home
                    date_from=date_from,
                    date_to=date_to
                    )
                self._bulk_upsert(raw_inbound)
                total_results += len(raw_inbound)
        
        return total_results

    def _bulk_upsert(self, api_flights):
        # Convert API objects to ORM objects and upsert
        # (Simplified for brevity - use bulk_save_objects or merge in prod)
        for f in api_flights:
            f_schema = FlightSchema(
                origin=f.origin,
                destination=f.destination,
                departure_time=f.departureTime,
                arrival_time=f.arrivalTime,
                flight_number=f.flightNumber,
                price=round(f.price, 2)
            )
            
            # SQLite upsert logic or simple check
            existing = self.db.query(Flight).filter_by(id=f_schema.unique_id).first()
            if existing:
                existing.price = f_schema.price
                existing.last_seen = datetime.now()
            else:
                new_flight = Flight(
                    id=f_schema.unique_id,
                    **f_schema.model_dump()
                )
                self.db.add(new_flight)
        self.db.commit()
