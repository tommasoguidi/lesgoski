# test_setup.py
import hashlib
from database.db import init_db, SessionLocal
from database.models import Flight, SearchProfile, Deal, StrategyConfig
from sqlalchemy.orm import joinedload
from services.scanner import FlightScanner
from services.matcher import DealMatcher
import argparse
import json


def generate_flight_id(flight_num, dep_time):
    raw = f"{flight_num}_{dep_time.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()

def run_test(scan: bool):
    print("--- Inizializzazione Database ---")
    init_db()
    db = SessionLocal()
    # Pulizia preliminare (opzionale, per rilanciare il test più volte)
    db.query(Deal).delete()
    if scan:
        db.query(Flight).delete()
    db.query(SearchProfile).delete()
    db.commit()
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
        # allowed_destinations="KRK",
    )
    profile.origins = ["PSA", "BLQ"]
    profile.strategy_object = strategy_config
    db.add(profile)
    db.commit()
    print(f"Profilo di ricerca creato: {profile.name}")

    if scan:
        print("\n--- Scanning flights... ---")
        scanner = FlightScanner()
        num_flights = scanner.run(origins=profile.origins, adults=profile.adults, days_horizon=60)
        print(f"Total flights found scanning: {num_flights}")

    print("\n--- Looking for deals... ---")
    matcher = DealMatcher()
    num_deals = matcher.run(profile)
    print(f"Total deals found: {num_deals}")
    
    if num_deals > 0:
        print("\n--- 5. Retrieving Saved Deals from DB ---")

        # Query Deals and eagerly load the related Flights
        # This executes 1 SQL query with JOINs instead of N+1 queries
        saved_deals = db.query(Deal).options(
            joinedload(Deal.outbound),
            joinedload(Deal.inbound)
        ).filter(Deal.profile_id == profile.id).order_by(
            Deal.total_price_pp.asc()  # Use .desc() if you want most expensive first
        ).all()
        for d in saved_deals:
            print(f"💰 Deal #{d.id} | Total: {d.total_price_pp} €")
            
            # You can now access .outbound and .inbound attributes directly
            # because they were populated by the query above
            out = d.outbound
            inb = d.inbound
            
            print(f"   🛫 Out: {out.origin_full} -> {out.destination_full} ({out.departure_time.strftime('%d/%m %H:%M')}) | {out.price}€")
            print(f"   🛬 In:  {inb.origin_full} -> {inb.destination_full} ({inb.departure_time.strftime('%d/%m %H:%M')}) | {inb.price}€")
            print("-" * 40)
    else:
        print("❌ No matching flights found.")

    db.close()

if __name__ == "__main__":
    args = argparse.ArgumentParser(description="Run flight scanner and matcher test.")
    args.add_argument("--scan", action="store_true", help="Run the flight scanner.")
    args = args.parse_args()
    run_test(scan=args.scan)
