# services/orchestrator.py
from sqlalchemy.orm import Session
from database.models import SearchProfile
from services.scanner import FlightScanner
from services.matcher import DealMatcher
from datetime import datetime
import traceback


def update_single_profile(db: Session, profile_id: int):
    """
    Runs the full Scanner -> Matcher cycle for a SINGLE profile.
    """
    profile = db.query(SearchProfile).get(profile_id)
    if not profile or not profile.is_active:
        print(f"Skipping update: Profile {profile_id} not found or inactive.")
        return

    print(f"--- [Orchestrator] Starting Update for: {profile.name} ---")
    try:
        # 1. SCAN: Fetch flights for this profile's origins
        scanner = FlightScanner(db=db)
        count_flights = scanner.run(profile)
        print(f"    > Scanned {count_flights} flights.")

        # 2. MATCH: Find deals for this profile
        matcher = DealMatcher(db=db)
        count_deals = matcher.run(profile) # This now commits internal deals
        print(f"    > Found {count_deals} matching deals.")

        # 3. UPDATE TIMESTAMP
        profile.updated_at = datetime.now()
        db.commit()
        print(f"--- [Orchestrator] Update Complete for {profile.name} ---")
    except Exception as e:
        db.rollback()
        print(f"❌ [Orchestrator] Update FAILED for {profile.name}")
        print(f"   Reason: {e}")
        traceback.print_exc()
