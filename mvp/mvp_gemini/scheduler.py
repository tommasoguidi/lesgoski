import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from services.orchestrator import run_full_update


logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    
    # Schedule every 6 hours
    scheduler.add_job(run_full_update, 'interval', hours=6)
    
    scheduler.start()
    print("Scheduler started. Press Ctrl+C to exit.")
    
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
