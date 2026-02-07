# services/scanner.py
import logging
import os
import time
from datetime import datetime, timedelta
from ryanair import Ryanair

logger = logging.getLogger(__name__)
from core.schemas import FlightSchema
from database.db import SessionLocal
from database.models import Flight, ScanLog
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

# Backend globals
SCAN_COOLDOWN_MINUTES = int(os.getenv("SCAN_COOLDOWN_MINUTES", 30))
LOOKUP_HORIZON_DAYS = int(os.getenv("LOOKUP_HORIZON_DAYS", 120))


class FlightScanner:
    def __init__(self, db: Session = None):
        self.api = Ryanair(currency="EUR")
        self.db = db or SessionLocal()

    def run(self, origins: list[str], adults: int) -> int:
        """
        Scan flights from the given origins for the given number of adults.
        Checks ScanLog to skip origins that were recently scanned.
        Returns total number of flights found.
        """
        today = datetime.now().date()
        date_from = today
        date_to = today + timedelta(days=LOOKUP_HORIZON_DAYS)
        total_results = 0
        cooldown_threshold = datetime.now() - timedelta(minutes=SCAN_COOLDOWN_MINUTES)

        for origin in origins:
            # Check if this (origin, adults) was scanned recently
            recent = self.db.query(ScanLog).filter(
                ScanLog.origin == origin,
                ScanLog.adults == adults,
                ScanLog.scanned_at > cooldown_threshold
            ).first()

            if recent:
                logger.info(f"Skipping {origin} (adults={adults}) — scanned at {recent.scanned_at}")
                continue

            logger.info(f"Scanning from {origin} (adults={adults})...")

            # 1. Scan One-Way Outbound (Origin -> Anywhere)
            raw_flights = self.api.get_cheapest_flights(
                airport=origin,
                num_adults=adults,
                date_from=date_from,
                date_to=date_to
            )
            self._bulk_upsert(raw_flights)
            total_results += len(raw_flights)
            # time.sleep(1)

            # 2. Scan return legs for each discovered destination
            destinations = {f.destination for f in raw_flights}

            for dest in destinations:
                raw_inbound = self.api.get_cheapest_flights(
                    airport=dest,
                    num_adults=adults,
                    destination_airport=origin,
                    date_from=date_from,
                    date_to=date_to
                )
                self._bulk_upsert(raw_inbound)
                total_results += len(raw_inbound)
                # time.sleep(1)

            # Log this scan
            self.db.add(ScanLog(
                origin=origin,
                adults=adults,
                scanned_at=datetime.now()
            ))
            self.db.flush()

        return total_results

    def _bulk_upsert(self, api_flights):
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

            flight_data = f_schema.model_dump()
            flight_data['id'] = f_schema.unique_id
            flight_data['updated_at'] = datetime.now()
            upsert_data.append(flight_data)

        if not upsert_data:
            return

        # Execute Upsert (chunked) — single PK on id
        chunk_size = 1000
        for i in range(0, len(upsert_data), chunk_size):
            chunk = upsert_data[i : i + chunk_size]
            stmt = sqlite_upsert(Flight).values(chunk)
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
