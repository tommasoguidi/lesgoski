"""Centralized configuration — all environment variables in one place."""

import os

from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./flights.db")

# Notifications
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "")

# Scanner
SCAN_COOLDOWN_MINUTES: int = int(os.getenv("SCAN_COOLDOWN_MINUTES", 30))
LOOKUP_HORIZON_DAYS: int = int(os.getenv("LOOKUP_HORIZON_DAYS", 120))

# Matcher
HOUR_TOLERANCE: int = int(os.getenv("HOUR_TOLERANCE", 1))

# Scheduler
UPDATE_INTERVAL_MINUTES: int = int(os.getenv("UPDATE_INTERVAL_MINUTES", 180))
FLIGHT_STALENESS_HOURS: int = int(os.getenv("FLIGHT_STALENESS_HOURS", 24))
