# test_setup.py
import hashlib
from database.db import init_db, SessionLocal
from database.models import Flight, SearchProfile, Deal, StrategyConfig
from sqlalchemy.orm import joinedload
from services.scanner import FlightScanner
from services.matcher import DealMatcher
from services.orchestrator import update_single_profile
import argparse
import json


def generate_flight_id(flight_num, dep_time):
    raw = f"{flight_num}_{dep_time.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()

def run_test(scan: bool):
    print("--- Inizializzazione Database ---")
    init_db()
    db = SessionLocal()
    print("Database creato/connesso con successo.")
    
    print("\n--- Configurazione Utente ---")
    # L'utente vuole andare ovunque da Pisa spendendo max 50€
    strategy_config = StrategyConfig(
        out_days={4: (17, 24), 5: (0, 12)},  # Ven-Sabato
        in_days={0: (0, 12), 6: (15, 24)},   # Dom-Lunedi
        min_stay=2,
        max_stay=3
    )
    profile = SearchProfile(
        name="Weekend Low Cost",
        max_price=80.0,
        adults=2,
        lookup_horizon=60,
        # allowed_destinations="KRK",
    )
    profile.origins = ["PSA", "BLQ"]
    profile.strategy_object = strategy_config
    db.add(profile)
    db.commit()
    print(f"Profilo di ricerca creato: {profile.name}")

    update_single_profile(db, profile.id)
    db.close()

if __name__ == "__main__":
    args = argparse.ArgumentParser(description="Run flight scanner and matcher test.")
    args.add_argument("--scan", action="store_true", help="Run the flight scanner.")
    args = args.parse_args()
    run_test(scan=args.scan)
