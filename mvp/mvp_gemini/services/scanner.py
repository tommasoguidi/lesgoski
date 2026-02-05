# services/scanner.py
from datetime import datetime, timedelta
from ryanair import Ryanair # Your existing lib
from core.schemas import FlightSchema
from database.db import SessionLocal
from database.models import Flight, SearchProfile
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert


class FlightScanner:
    def __init__(self, db: Session = None):
        self.api = Ryanair(currency="EUR")
        self.db = db or SessionLocal()

    def run(self, profile: SearchProfile) -> int:
        """
        Dumb-scan: Just get all flights from origins for X days.
        Returns total number of flights found.
        """
        today = datetime.now().date()
        date_from = today
        date_to = today + timedelta(days=profile.lookup_horizon or 60)
        total_results = 0
        
        for origin in profile.origins:
            print(f"Scanning from {origin}...")
            
            # 1. Scan One-Way Outbound (Origin -> Anywhere)
            # Note: Ryanair API requires a destination usually, or specialized "farefinder"
            # If using "farefinder" API (get_cheapest_flights), we can often leave dest empty
            raw_flights = self.api.get_cheapest_flights(
                airport=origin,
                num_adults=profile.adults,
                date_from=date_from,
                date_to=date_to
            )
            self._bulk_upsert(raw_flights, profile.id)
            total_results += len(raw_flights)

            # 2. To build Round Trips, we ideally need the return legs.
            # In a "hub" model (PSA -> X), we need to scan X -> PSA.
            # Since we don't know X yet, we extract distinct destinations from step 1
            destinations = {f.destination for f in raw_flights}
            
            for dest in destinations:
                # Scan One-Way Inbound (Anywhere -> Origin)
                raw_inbound = self.api.get_cheapest_flights(
                    airport=dest,
                    num_adults=profile.adults,
                    destination_airport=origin, # Explicitly back to home
                    date_from=date_from,
                    date_to=date_to
                    )
                self._bulk_upsert(raw_inbound, profile.id)
                total_results += len(raw_inbound)
        
        # 2. PRUNE Operations
        # Since _bulk_upsert used db.execute(), the database cursor is up to date 
        # within this transaction. The DELETE will see the upserted rows.
        threshold = datetime.now() - timedelta(minutes=10)
        
        # We don't need to commit/rollback here. 
        # If this fails, the exception bubbles up to Orchestrator.
        self.db.query(Flight).filter(
            Flight.profile_id == profile.id,
            Flight.updated_at < threshold
        ).delete()
        
        return total_results

    def _bulk_upsert(self, api_flights, profile_id: int):
        if not api_flights:
            return

        upsert_data = []
        for f in api_flights:
            f_schema = FlightSchema(
                departure_time=f.departureTime,
                arrival_time=f.arrivalTime,
                flight_number=f.flightNumber,
                price=round(f.price, 2),
                currency=f.currency,
                origin=f.origin,
                origin_full=f.originFull,
                destination=f.destination,
                destination_full=f.destinationFull,
                adults=f.adults,
            )
            
            # Create a flight object with all data
            flight_data = f_schema.model_dump()
            flight_data['id'] = f_schema.unique_id
            flight_data['profile_id'] = profile_id
            flight_data['updated_at'] = datetime.now()
            upsert_data.append(flight_data)
            
        if not upsert_data:
            return

        # Execute Upsert
        stmt = sqlite_upsert(Flight).values(upsert_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['id'],
            set_={
                'price': stmt.excluded.price,
                'updated_at': stmt.excluded.updated_at,
                'departure_time': stmt.excluded.departure_time,
                'arrival_time': stmt.excluded.arrival_time
            }
        )
        self.db.execute(stmt)

