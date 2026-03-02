# scheduler/runner.py
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import schedule
from datetime import datetime, timedelta
from lesgoski.config import UPDATE_INTERVAL_MINUTES, FLIGHT_STALENESS_HOURS
from lesgoski.database.engine import SessionLocal
from lesgoski.database.models import SearchProfile, Flight, ScanLog, Deal
from lesgoski.services.orchestrator import update_single_profile
from lesgoski.services.notifier import send_daily_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

MAX_WORKERS = 3


def _update_profile_thread(profile_id: int, profile_name: str):
    """Run a single profile update in its own thread with a fresh DB session."""
    db = SessionLocal()
    try:
        update_single_profile(db, profile_id)
    except Exception as e:
        logger.error(f"Error updating profile {profile_name}: {e}", exc_info=True)
    finally:
        db.close()


def check_and_run_updates():
    """
    Polls the database for profiles that are due for an update.
    A profile is due if updated_at is NULL or older than UPDATE_INTERVAL_MINUTES.
    Runs due profiles in parallel using a thread pool.
    """
    db = SessionLocal()
    try:
        profiles = db.query(SearchProfile).filter(SearchProfile.is_active).all()
        now = datetime.now()
        threshold = now - timedelta(minutes=UPDATE_INTERVAL_MINUTES)

        due_profiles = []
        for profile in profiles:
            if not profile.updated_at or profile.updated_at < threshold:
                due_profiles.append((profile.id, profile.name))

    except Exception as e:
        logger.error(f"Error in scheduler loop: {e}", exc_info=True)
        return
    finally:
        db.close()

    if not due_profiles:
        return

    logger.info(f"Scheduling updates for {len(due_profiles)} profile(s)")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_update_profile_thread, pid, name): name
            for pid, name in due_profiles
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Thread for {name} raised: {e}", exc_info=True)


def prune_stale_data():
    """Remove stale flights and old scan_log entries."""
    db = SessionLocal()
    try:
        now = datetime.now()

        # Prune flights older than FLIGHT_STALENESS_HOURS
        stale_threshold = now - timedelta(hours=FLIGHT_STALENESS_HOURS)
        deleted_flights = db.query(Flight).filter(
            Flight.updated_at < stale_threshold
        ).delete()

        # Prune deals whose flights were just deleted (orphaned FKs)
        orphaned_deals = db.query(Deal).filter(
            ~Deal.outbound_flight_id.in_(db.query(Flight.id)) |
            ~Deal.inbound_flight_id.in_(db.query(Flight.id))
        ).delete(synchronize_session="fetch")

        # Prune scan_log entries older than 7 days
        old_logs = db.query(ScanLog).filter(
            ScanLog.scanned_at < now - timedelta(days=7)
        ).delete()

        db.commit()
        if deleted_flights or orphaned_deals or old_logs:
            logger.info(f"Pruned {deleted_flights} stale flights, {orphaned_deals} orphaned deals, {old_logs} old scan logs")
    except Exception as e:
        db.rollback()
        logger.error(f"Pruning failed: {e}", exc_info=True)
    finally:
        db.close()


def run_daily_digest():
    """Send a daily summary of the best deals across all profiles."""
    db = SessionLocal()
    try:
        send_daily_digest(db)
    except Exception as e:
        logger.error(f"Daily digest failed: {e}", exc_info=True)
    finally:
        db.close()


def main():
    """Entry point for the scheduler."""
    logger.info("Starting Polling Scheduler...")

    schedule.every(5).minutes.do(check_and_run_updates)
    schedule.every(1).hours.do(prune_stale_data)
    schedule.every().day.at("08:00").do(run_daily_digest)

    # Run once immediately on startup to catch up
    check_and_run_updates()

    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    main()
