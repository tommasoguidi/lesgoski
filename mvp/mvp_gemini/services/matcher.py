# services/matcher.py
from sqlalchemy.orm import aliased
from database.models import Flight, SearchProfile, Deal
from database.db import SessionLocal
from datetime import datetime
from core.schemas import StrategyConfig


class DealMatcher:
    def __init__(self):
        self.db = SessionLocal()

    def run(self, profile: SearchProfile) -> int:
        """
        Reconstructs round trips from the atomic flights table
        based on profile rules.
        returns number of deals found.
        """
        # Load constraints
        config = profile.strategy_object
        if not config:
            print(f"⚠️ Profile {profile.name} has no strategy config.")
            return []

        home_airports = profile.origins
        Outbound = aliased(Flight)
        Inbound = aliased(Flight)

        # Build candidates
        candidates = self.db.query(Outbound, Inbound).join(
            Inbound,
            (Outbound.destination == Inbound.origin)
        ).filter(
            # A -> B
            Outbound.origin.in_(home_airports),
            
            # B -> C (where C is also a home airport)
            Inbound.destination.in_(home_airports),
            
            # Price Filter
            (Outbound.price + Inbound.price) <= profile.max_price,
            
            # Time Logic
            Inbound.departure_time > Outbound.arrival_time
        ).all()
        
        num_matches = 0
        for out_f, in_f in candidates:
            if self._is_valid_match(out_f, in_f, config):
                self._create_deal(profile, out_f, in_f)
                num_matches += 1
        self.db.commit()
        
        return num_matches

    def _is_valid_match(self, out_f: Flight, in_f: Flight, config: StrategyConfig) -> bool:
        # 1. Check Stay Duration (Days)
        # Calculate difference in days
        delta = in_f.departure_time.date() - out_f.departure_time.date()
        days_stay = delta.days + 1  # fammoc se sto sabato e domenica sono 2gg
        
        if not (config.min_stay <= days_stay <= config.max_stay):
            return False

        # 2. Check Outbound Day & Time
        out_dow = out_f.departure_time.weekday()
        if out_dow not in config.out_days:
            return False
        
        min_h, max_h = config.out_days[out_dow]
        if not (min_h <= out_f.departure_time.hour < max_h):
            return False

        # 3. Check Inbound Day & Time
        in_dow = in_f.departure_time.weekday()
        if in_dow not in config.in_days:
            return False
            
        min_h, max_h = config.in_days[in_dow]
        if not (min_h <= in_f.departure_time.hour < max_h):
            return False

        return True

    def _create_deal(self, profile, out_f, in_f):
        # Create Deal record in DB
        # Create the Deal record
            deal = Deal(
                profile_id=profile.id,
                outbound_flight_id=out_f.id,
                inbound_flight_id=in_f.id,
                total_price=round(out_f.price + in_f.price, 2),
                found_at=datetime.now(),
                notified=False
            )
            self.db.add(deal)
