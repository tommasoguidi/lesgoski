# test_setup.py
import logging
import argparse
from database.db import init_db, SessionLocal
from database.models import SearchProfile
from core.schemas import StrategyConfig
from services.orchestrator import update_single_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_test(scan: bool):
    logger.info("Initializing database...")
    init_db()
    db = SessionLocal()

    strategy_config = StrategyConfig(
        out_days={4: (17, 24), 5: (0, 12)},  # Fri-Sat
        in_days={0: (0, 12), 6: (15, 24)},   # Sun-Mon
        min_nights=1,
        max_nights=2
    )
    profile = SearchProfile(
        name="Weekend Low Cost",
        max_price=80.0,
        adults=2,
    )
    profile.origins = ["PSA", "BLQ"]
    profile.strategy_object = strategy_config
    db.add(profile)
    db.commit()
    logger.info(f"Search profile created: {profile.name}")

    update_single_profile(db, profile.id)
    db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run flight scanner and matcher test.")
    parser.add_argument("--scan", action="store_true", help="Run the flight scanner.")
    args = parser.parse_args()
    run_test(scan=args.scan)
