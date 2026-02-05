# scheduler.py
import time
import schedule
from datetime import datetime, timedelta
from database.db import SessionLocal
from database.models import SearchProfile
from services.orchestrator import update_single_profile

def check_and_run_updates():
    """
    Polls the database for profiles that are due for an update.
    """
    db = SessionLocal()
    try:
        profiles = db.query(SearchProfile).filter(SearchProfile.is_active == True).all()
        
        now = datetime.now()
        
        for profile in profiles:
            interval = profile.update_interval_hours or 12
            last_run = profile.updated_at
            
            is_due = False
            if not last_run:
                is_due = True # Never run before
            elif (now - last_run) > timedelta(hours=interval):
                is_due = True
            
            if is_due:
                print(f"⏰ Triggering scheduled update for {profile.name} (Last run: {last_run})")
                try:
                    update_single_profile(db, profile.id)
                except Exception as e:
                    print(f"❌ Error updating profile {profile.name}: {e}")
                    
    except Exception as e:
        print(f"Error in scheduler loop: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    print("Starting Polling Scheduler...")
    
    # Check every minute if any profile is due
    schedule.every(1).minutes.do(check_and_run_updates)
    
    # Run once immediately on startup to catch up
    check_and_run_updates()

    while True:
        schedule.run_pending()
        time.sleep(10)
