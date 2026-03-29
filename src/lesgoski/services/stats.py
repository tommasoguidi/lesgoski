# services/stats.py
import logging
from datetime import datetime, date, timedelta
from statistics import mean
from sqlalchemy.orm import Session
from lesgoski.database.models import Deal, PriceSnapshot, SearchProfile
from lesgoski.services.grouping import group_deals_by_destination

logger = logging.getLogger(__name__)


def record_price_snapshots(db: Session, profile: SearchProfile):
    """
    Called after each matcher run. Inserts or updates one PriceSnapshot row
    per (profile, destination) per calendar day, keeping the day's lowest price.
    """
    deals = [
        d for d in db.query(Deal).filter(Deal.profile_id == profile.id).all()
        if d.outbound and d.inbound
    ]
    if not deals:
        return

    groups = group_deals_by_destination(deals)
    today = date.today()
    today_start = datetime(today.year, today.month, today.day)
    today_end = datetime(today.year, today.month, today.day, 23, 59, 59)

    for group in groups:
        dest_code = group["destination_code"]
        best_deal = group["best_deal"]
        price = best_deal.total_price_pp
        departure = best_deal.outbound.departure_time
        advance_days = max(0, (departure.date() - today).days)

        existing = db.query(PriceSnapshot).filter(
            PriceSnapshot.profile_id == profile.id,
            PriceSnapshot.destination_code == dest_code,
            PriceSnapshot.recorded_at >= today_start,
            PriceSnapshot.recorded_at <= today_end,
        ).first()

        if existing:
            if price < existing.best_price:
                existing.best_price = price
                existing.advance_days = advance_days
        else:
            db.add(PriceSnapshot(
                profile_id=profile.id,
                destination_code=dest_code,
                best_price=price,
                advance_days=advance_days,
                recorded_at=datetime.now(),
            ))

    logger.debug(f"Recorded price snapshots for profile {profile.id} ({len(groups)} destinations)")


def get_all_destination_stats(db: Session, profile_id: int):
    """
    Batch-fetches all snapshots for a profile and returns a dict keyed by
    destination_code. Each value is None (< 3 data points) or:
      { avg_price, min_price, avg_advance_days, count }
    """
    cutoff = datetime.now() - timedelta(days=90)
    snapshots = db.query(PriceSnapshot).filter(
        PriceSnapshot.profile_id == profile_id,
        PriceSnapshot.recorded_at >= cutoff,
    ).all()

    by_dest = {}
    for s in snapshots:
        by_dest.setdefault(s.destination_code, []).append(s)

    result = {}
    for dest_code, snaps in by_dest.items():
        if len(snaps) < 3:
            result[dest_code] = None
            continue
        result[dest_code] = {
            "avg_price": round(mean(s.best_price for s in snaps), 0),
            "avg_advance_days": round(mean(s.advance_days for s in snaps)),
            "count": len(snaps),
        }

    return result


def get_destination_stats(db: Session, profile_id: int, destination_code: str):
    """Stats for a single destination. Returns None if fewer than 3 data points."""
    all_stats = get_all_destination_stats(db, profile_id)
    return all_stats.get(destination_code)
