# services/orchestrator.py
import logging
from database.db import SessionLocal
from database.models import SearchProfile
from services.scanner import FlightScanner
from services.matcher import DealMatcher
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

def run_full_update(db_session: Session = None):
    """
    Orchestrates the refresh of flights and the re-matching of deals.
    """
    db = db_session or SessionLocal()
    try:
        scanner = FlightScanner()
        matcher = DealMatcher()
        profiles = db.query(SearchProfile).filter(SearchProfile.is_active == True).all()
        
        if not profiles:
            return
        
        # Group origins by adult count: {1: {'PSA', 'BLQ'}, 2: {'PSA'}}
        scan_groups = {}
        for p in profiles:
            if p.adults not in scan_groups:
                scan_groups[p.adults] = set()
            scan_groups[p.adults].update(p.origins)

        # Run scans for each group
        for adult_count, origins in scan_groups.items():
            scanner.run(origins=list(origins), adults=adult_count)

        for profile in profiles:
            matcher.run(profile)
            
    except Exception as e:
        logger.error(f"Error during scheduled update: {e}")
    finally:
        db.close()
