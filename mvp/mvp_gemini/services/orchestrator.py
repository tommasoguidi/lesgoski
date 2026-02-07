# services/orchestrator.py
import logging
from sqlalchemy.orm import Session
from database.models import SearchProfile
from services.scanner import FlightScanner
from services.matcher import DealMatcher
from services.notifier import notify_new_deals
from datetime import datetime

logger = logging.getLogger(__name__)


def update_single_profile(db: Session, profile_id: int):
    """
    Runs the full Scanner -> Matcher -> Notifier cycle for a SINGLE profile.
    The scanner internally deduplicates via ScanLog to avoid repeated API calls.
    """
    profile = db.get(SearchProfile, profile_id)
    if not profile or not profile.is_active:
        logger.info(f"Skipping update: Profile {profile_id} not found or inactive.")
        return

    logger.info(f"Starting update for: {profile.name}")
    try:
        # 1. Scan (with dedup via ScanLog)
        scanner = FlightScanner(db=db)
        count_flights = scanner.run(origins=profile.origins, adults=profile.adults)
        logger.info(f"  Scanned {count_flights} flights.")

        # 2. Match flights into deals
        matcher = DealMatcher(db=db)
        count_deals = matcher.run(profile)
        logger.info(f"  Found {count_deals} matching deals.")

        # 3. Send push notifications for new deals
        notify_new_deals(db, profile)

        # 4. Mark profile as updated
        profile.updated_at = datetime.now()
        db.commit()
        logger.info(f"Update complete for {profile.name}")
    except Exception as e:
        db.rollback()
        logger.error(f"Update FAILED for {profile.name}: {e}", exc_info=True)
