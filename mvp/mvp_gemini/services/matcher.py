# services/matcher.py
import logging
import os
from sqlalchemy.orm import aliased, Session
from database.models import Flight, SearchProfile, Deal
from database.db import SessionLocal
from datetime import datetime
from core.schemas import StrategyConfig

logger = logging.getLogger(__name__)

# Tolerance: allow flights up to HOUR_TOLERANCE hours outside the user's time window
HOUR_TOLERANCE = int(os.getenv("HOUR_TOLERANCE", 1))


class DealMatcher:
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def run(self, profile: SearchProfile) -> int:
        """
        Reconstructs round trips from the shared flights table
        based on profile rules (origins, adults, strategy, price).
        Returns number of deals found.
        """
        match_start = datetime.now()

        # Load constraints
        config = profile.strategy_object
        if not config:
            logger.warning(f"Profile {profile.name} has no strategy config.")
            return 0

        home_airports = profile.origins
        adults = float(profile.adults)
        Outbound = aliased(Flight)
        Inbound = aliased(Flight)

        # Query the shared flights table — filter by origins and adults
        query = self.db.query(Outbound, Inbound).join(
            Inbound,
            (Outbound.destination == Inbound.origin)
        ).filter(
            Outbound.origin.in_(home_airports),
            Outbound.adults == profile.adults,
            Inbound.destination.in_(home_airports),
            Inbound.adults == profile.adults,
            (Outbound.price + Inbound.price) / adults <= profile.max_price * 1.25,
            Inbound.departure_time > Outbound.arrival_time
        )

        # Apply allowed destinations filter if configured
        allowed = profile.allowed_destinations
        if allowed:
            query = query.filter(Outbound.destination.in_(allowed))

        candidates = query.all()

        num_matches = 0
        for out_f, in_f in candidates:
            if self._is_valid_match(out_f, in_f, config):
                self._create_deal(profile, out_f, in_f)
                num_matches += 1
        self.db.flush()

        # Prune deals that were not refreshed during this matching run.
        self.db.query(Deal).filter(
            Deal.profile_id == profile.id,
            Deal.updated_at < match_start
        ).delete()

        return num_matches

    def _is_valid_match(self, out_f: Flight, in_f: Flight, config: StrategyConfig) -> bool:
        # 1. Check Stay Duration (Nights)
        nights = (in_f.departure_time.date() - out_f.departure_time.date()).days

        if not (config.min_nights <= nights <= config.max_nights):
            return False

        # 2. Check Outbound Day & Time (with tolerance)
        out_dow = out_f.departure_time.weekday()
        if out_dow not in config.out_days:
            return False

        min_h, max_h = config.out_days[out_dow]
        if not (max(0, min_h - HOUR_TOLERANCE) <= out_f.departure_time.hour < min(24, max_h + HOUR_TOLERANCE)):
            return False

        # 3. Check Inbound Day & Time (with tolerance)
        in_dow = in_f.departure_time.weekday()
        if in_dow not in config.in_days:
            return False

        min_h, max_h = config.in_days[in_dow]
        if not (max(0, min_h - HOUR_TOLERANCE) <= in_f.departure_time.hour < min(24, max_h + HOUR_TOLERANCE)):
            return False

        return True

    def _create_deal(self, profile, out_f, in_f):
        # Check if this deal already exists for this profile
        existing = self.db.query(Deal).filter_by(
            profile_id=profile.id,
            outbound_flight_id=out_f.id,
            inbound_flight_id=in_f.id
        ).first()

        adults = float(profile.adults)
        actual_price_pp = round(out_f.price + in_f.price, 2)
        if existing:
            existing.updated_at = datetime.now()
            if existing.total_price_pp != actual_price_pp:
                # prezzo cambiato, aggiorno
                existing.total_price_pp = actual_price_pp
                existing.notified = False
        else:
            new_deal = Deal(
                profile_id=profile.id,
                outbound_flight_id=out_f.id,
                inbound_flight_id=in_f.id,
                total_price_pp=actual_price_pp,
                updated_at=datetime.now(),
                notified=False
            )
            self.db.add(new_deal)
