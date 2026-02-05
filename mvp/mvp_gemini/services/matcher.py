# services/matcher.py
from sqlalchemy.orm import aliased
from database.models import Flight, SearchProfile, Deal
from database.db import SessionLocal
from datetime import datetime, timedelta
from core.schemas import StrategyConfig
from sqlalchemy.orm import Session


class DealMatcher:
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

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
        adults = float(profile.adults)
        Outbound = aliased(Flight)
        Inbound = aliased(Flight)

        # 1. Start with the base query and mandatory filters
        query = self.db.query(Outbound, Inbound).join(
            Inbound,
            (Outbound.destination == Inbound.origin)
        ).filter(
            Outbound.origin.in_(home_airports),
            Inbound.destination.in_(home_airports),
            (Outbound.price + Inbound.price) / adults <= profile.max_price * 1.25,  # Allow 25% tolerance
            Inbound.departure_time > Outbound.arrival_time
        )

        # 3. Execute the query
        candidates = query.all()
        
        num_matches = 0
        for out_f, in_f in candidates:
            if self._is_valid_match(out_f, in_f, config):
                self._create_deal(profile, out_f, in_f)
                num_matches += 1
        
        # 2. Prune old deals
        # If a deal wasn't updated in this run, it means the flights no longer exist
        # We'll use a 10-minute buffer to be safe
        threshold = datetime.now() - timedelta(minutes=10)
        self.db.query(Deal).filter(
            Deal.profile_id == profile.id,
            Deal.updated_at < threshold
        ).delete()
        
        self.db.commit()
        
        return num_matches

    def _is_valid_match(self, out_f: Flight, in_f: Flight, config: StrategyConfig) -> bool:
        # 1. Check Stay Duration (Days)
        # Calculate difference in days
        delta = in_f.departure_time.date() - out_f.departure_time.date()
        days_stay = delta.days + 1  # fammoc se sto sabato e domenica sono 2gg (delta è 1)
        
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
        # Check if this deal already exists for this profile
        existing = self.db.query(Deal).filter_by(
            profile_id=profile.id,
            outbound_flight_id=out_f.id,
            inbound_flight_id=in_f.id
        ).first()

        adults = float(profile.adults)
        if existing:
            # c'era già
            actual_price_pp = round((out_f.price + in_f.price) / adults, 2)
            if existing.total_price_pp != actual_price_pp:
                # prezzo cambiato, aggiorno
                existing.total_price_pp = actual_price_pp
                existing.updated_at = datetime.now()
                existing.notified = False
            else:
                # non è cambiato il prezzo ma l'offerta c'è ancora
                existing.updated_at = datetime.now()
        else:
            deal = Deal(
                profile_id=profile.id,
                outbound_flight_id=out_f.id,
                inbound_flight_id=in_f.id,
                total_price_pp=round((out_f.price + in_f.price) / adults, 2),
                updated_at=datetime.now(),
                notified=False
            )
            self.db.add(deal)
