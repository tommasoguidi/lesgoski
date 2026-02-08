# services/notifier.py
import logging
import requests
from sqlalchemy.orm import Session, joinedload
from lesgoski.database.models import Deal, SearchProfile
from lesgoski.config import NTFY_TOPIC

logger = logging.getLogger(__name__)

NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}" if NTFY_TOPIC else None


def _build_booking_url(deal: Deal) -> str:
    """Build a simple Ryanair search URL for the deal."""
    out = deal.outbound
    adults = deal.profile.adults or 1
    d_out = out.departure_time.strftime("%Y-%m-%d")
    d_in = deal.inbound.departure_time.strftime("%Y-%m-%d")
    return (
        f"https://www.ryanair.com/it/it/trip/flights/select"
        f"?adults={adults}&teens=0&children=0&infants=0"
        f"&dateOut={d_out}&dateIn={d_in}"
        f"&originIata={out.origin}&destinationIata={out.destination}"
        f"&isReturn=true"
    )


def notify_new_deals(db: Session, profile: SearchProfile) -> int:
    """
    Send an immediate push notification for new deals that are
    within budget and haven't been notified yet.
    Returns the number of notifications sent.
    """
    if not NTFY_URL:
        logger.warning("NTFY_TOPIC not set, skipping notifications.")
        return 0

    new_deals = (
        db.query(Deal)
        .options(joinedload(Deal.outbound), joinedload(Deal.inbound), joinedload(Deal.profile))
        .filter(
            Deal.profile_id == profile.id,
            Deal.notified == False,
            Deal.total_price_pp <= profile.max_price,
        )
        .order_by(Deal.total_price_pp)
        .all()
    )

    if not new_deals:
        return 0

    # Group deals by destination for a cleaner notification
    by_dest = {}
    for deal in new_deals:
        dest = deal.outbound.destination
        if dest not in by_dest:
            by_dest[dest] = deal  # keep the cheapest (already sorted)

    # Only send immediate notifications for destinations the user has "belled"
    notify_dests = profile.notify_destinations
    if notify_dests:
        by_dest = {dest: deal for dest, deal in by_dest.items() if dest in notify_dests}
    else:
        # No bells toggled → no immediate notifications (opt-in model)
        by_dest = {}

    if not by_dest:
        # Mark all as notified even if we didn't send (avoids re-checking next run)
        for deal in new_deals:
            deal.notified = True
        db.flush()
        return 0

    for dest, deal in by_dest.items():
        out = deal.outbound
        inb = deal.inbound
        dest_name = (out.destination_full or dest).split(",")[0].strip()
        out_date = out.departure_time.strftime("%a %d %b")
        in_date = inb.departure_time.strftime("%a %d %b")

        title = f"{dest_name} {deal.total_price_pp:.0f}EUR pp"
        body = f"{out.origin} -> {dest} {out_date} / {in_date}"
        url = _build_booking_url(deal)

        try:
            requests.post(
                NTFY_URL,
                headers={
                    "Title": title,
                    "Click": url,
                    "Tags": "airplane",
                    "Priority": "3",
                },
                data=body,
                timeout=10,
            )
        except Exception as e:
            logger.error(f"Failed to send notification for {dest}: {e}")

    # Mark all as notified
    for deal in new_deals:
        deal.notified = True
    db.flush()

    logger.info(f"Sent {len(by_dest)} notifications for profile {profile.name}")
    return len(by_dest)


def send_daily_digest(db: Session) -> int:
    """
    Send a single digest notification summarizing the best deal
    per destination across all active profiles.
    Returns the number of destinations included.
    """
    if not NTFY_URL:
        return 0

    profiles = db.query(SearchProfile).filter(SearchProfile.is_active == True).all()
    if not profiles:
        return 0

    # Collect best deal per destination across all profiles
    best_by_dest = {}
    for profile in profiles:
        deals = (
            db.query(Deal)
            .options(joinedload(Deal.outbound), joinedload(Deal.inbound), joinedload(Deal.profile))
            .filter(
                Deal.profile_id == profile.id,
                Deal.total_price_pp <= profile.max_price,
            )
            .order_by(Deal.total_price_pp)
            .all()
        )
        for deal in deals:
            dest = deal.outbound.destination
            if dest not in best_by_dest or deal.total_price_pp < best_by_dest[dest].total_price_pp:
                best_by_dest[dest] = deal

    if not best_by_dest:
        return 0

    # Build digest message
    lines = []
    sorted_deals = sorted(best_by_dest.values(), key=lambda d: d.total_price_pp)
    for deal in sorted_deals[:15]:  # top 15 to keep it readable
        out = deal.outbound
        dest_name = (out.destination_full or out.destination).split(",")[0].strip()
        out_date = out.departure_time.strftime("%d/%m")
        in_date = deal.inbound.departure_time.strftime("%d/%m")
        lines.append(f"{dest_name}: {deal.total_price_pp:.0f}EUR ({out_date}-{in_date})")

    body = "\n".join(lines)

    try:
        requests.post(
            NTFY_URL,
            headers={
                "Title": f"Daily Flight Digest ({len(best_by_dest)} destinations)",
                "Tags": "globe_with_meridians",
                "Priority": "3",
            },
            data=body,
            timeout=10,
        )
        logger.info(f"Daily digest sent with {len(best_by_dest)} destinations")
    except Exception as e:
        logger.error(f"Failed to send daily digest: {e}")

    return len(best_by_dest)


def notify_new_deals_for_profile(db: Session, profile_id: int) -> int:
    """Convenience function to notify new deals for a specific profile."""
    profile = db.get(SearchProfile, profile_id)
    if not profile:
        logger.warning(f"Profile ID {profile_id} not found for notifications.")
        return 0
    return notify_new_deals(db, profile)
