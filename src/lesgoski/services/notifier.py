# services/notifier.py
import logging
import requests
from sqlalchemy.orm import Session, joinedload
from lesgoski.database.models import Deal, SearchProfile
from lesgoski.config import NTFY_TOPIC, WEBAPP_URL

logger = logging.getLogger(__name__)


def _get_ntfy_url(profile: SearchProfile) -> str | None:
    """Resolve the ntfy URL for a profile: per-user topic first, global fallback."""
    topic = None
    if profile.user and profile.user.ntfy_topic:
        topic = profile.user.ntfy_topic
    elif NTFY_TOPIC:
        topic = NTFY_TOPIC
    if not topic:
        return None
    return f"https://ntfy.sh/{topic}"


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


def _webapp_deal_url(profile_id: int, dest_code: str) -> str:
    """Deep-link to a specific deal card in the webapp."""
    return f"{WEBAPP_URL}/?profile_id={profile_id}#deal-{dest_code}"


def _webapp_profile_url(profile_id: int) -> str:
    """Link to the webapp filtered to a specific profile."""
    return f"{WEBAPP_URL}/?profile_id={profile_id}"


def notify_new_deals(db: Session, profile: SearchProfile):
    """
    Send push notifications for new deals:
    1. Per-destination notifications for "belled" destinations (click → webapp deep-link)
    2. A generic summary notification if there are un-belled new deals
    """
    ntfy_url = _get_ntfy_url(profile)
    if not ntfy_url:
        logger.warning("No ntfy topic for profile %s, skipping notifications.", profile.name)
        return

    actual_deals = (
        db.query(Deal)
        .options(joinedload(Deal.outbound), joinedload(Deal.inbound), joinedload(Deal.profile))
        .filter(
            Deal.profile_id == profile.id,
        )
        .order_by(Deal.total_price_pp)
        .all()
    )

    if not actual_deals:
        return

    # Group deals by destination — keep the cheapest (already sorted)
    by_dest = {}
    for deal in actual_deals:
        dest = deal.outbound.destination
        if dest not in by_dest:
            by_dest[dest] = deal

    notify_dests = set(profile.notify_destinations or [])
    sent = 0

    # --- Belled destination notifications (click → webapp deep-link) ---
    belled = {dest: deal for dest, deal in by_dest.items() if dest in notify_dests}

    for dest, deal in belled.items():
        out = deal.outbound
        inb = deal.inbound
        dest_name = (out.destination_full or dest).split(",")[0].strip()
        out_date = out.departure_time.strftime("%a %d %b")
        in_date = inb.departure_time.strftime("%a %d %b")

        title = f"{dest_name} {deal.total_price_pp:.0f}EUR pp"
        body = f"{out.origin} -> {dest} {out_date} / {in_date}"
        url = _webapp_deal_url(profile.id, dest)

        try:
            requests.post(
                ntfy_url,
                headers={
                    "Title": title,
                    "Click": url,
                    "Tags": "airplane",
                    "Priority": "3",
                },
                data=body,
                timeout=10,
            )
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send notification for {dest}: {e}")

    # --- Generic summary for un-belled new deals ---
    unbelled = {dest: deal for dest, deal in by_dest.items() if dest not in notify_dests}

    if unbelled:
        # Top 3 cheapest un-belled destinations
        top3 = sorted(unbelled.values(), key=lambda d: d.total_price_pp)[:3]
        summary_parts = []
        for deal in top3:
            dest_name = (deal.outbound.destination_full or deal.outbound.destination).split(",")[0].strip()
            summary_parts.append(f"{dest_name} {deal.total_price_pp:.0f}€")

        title = f"{profile.name}: {len(unbelled)} new deals"
        body = " | ".join(summary_parts)
        url = _webapp_profile_url(profile.id)

        try:
            requests.post(
                ntfy_url,
                headers={
                    "Title": title,
                    "Click": url,
                    "Tags": "chart_with_upwards_trend",
                    "Priority": "2",
                },
                data=body,
                timeout=10,
            )
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send generic summary for {profile.name}: {e}")

    # Mark all as notified
    for deal in actual_deals:
        deal.notified = True
    db.flush()

    logger.info(f"Sent {sent} notifications for profile {profile.name}")


def send_daily_digest(db: Session):
    """
    Send a single digest notification summarizing the best deal
    per destination across all active profiles.
    """
    profiles = (
        db.query(SearchProfile)
        .options(joinedload(SearchProfile.user))
        .filter(SearchProfile.is_active == True)
        .all()
    )
    if not profiles:
        return

    # Collect best deal per destination for each profile
    for profile in profiles:
        best_by_dest = {}
        deals = (
            db.query(Deal)
            .options(joinedload(Deal.outbound), joinedload(Deal.inbound), joinedload(Deal.profile))
            .filter(
                Deal.profile_id == profile.id,
            )
            .order_by(Deal.total_price_pp)
            .all()
        )
        for deal in deals:
            dest = deal.outbound.destination
            if dest not in best_by_dest:  # already ordered
                best_by_dest[dest] = deal

        if not best_by_dest:
            continue

        ntfy_url = _get_ntfy_url(profile)
        if not ntfy_url:
            continue

        # Build digest message
        lines = []
        for deal in list(best_by_dest.values())[:15]:  # top 15 to keep it readable
            out = deal.outbound
            dest_name = (out.destination_full or out.destination).split(",")[0].strip()
            out_date = out.departure_time.strftime("%d/%m")
            in_date = deal.inbound.departure_time.strftime("%d/%m")
            lines.append(f"{dest_name}: {deal.total_price_pp:.0f}EUR ({out_date}-{in_date})")

        body = "\n".join(lines)

        try:
            requests.post(
                ntfy_url,
                headers={
                    "Title": f"Daily Flight Digest - {profile.name}",
                    "Click": f"{WEBAPP_URL}/",
                    "Tags": "globe_with_meridians",
                    "Priority": "3",
                },
                data=body,
                timeout=10,
            )
            logger.info(f"Daily digest sent for profile {profile.name} destinations")
        except Exception as e:
            logger.error(f"Failed to send daily digest: {e}")
