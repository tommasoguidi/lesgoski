# webapp/utils.py
import json
import os
import urllib.parse
from functools import lru_cache
from lesgoski.database.models import Deal, Flight

_WEBAPP_DIR = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=1)
def _load_country_mapping() -> dict:
    """Load alpha-2 country codes once and build lookup structures."""
    path = os.path.join(_WEBAPP_DIR, "data", "slim-2.json")
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    # exact name → code
    exact = {}
    # list of (lowercase_name, code) for fuzzy fallback
    all_entries = []
    for entry in entries:
        name_lower = entry["name"].lower()
        code = entry["alpha-2"]
        exact[name_lower] = code
        all_entries.append((name_lower, code))

    return {"exact": exact, "all": all_entries}


def get_country_code(full_name: str) -> str:
    if not full_name:
        return "EU"

    country_name = full_name.split(",")[-1].strip().lower()
    mapping = _load_country_mapping()

    # 1. Exact match
    if country_name in mapping["exact"]:
        return mapping["exact"][country_name]

    # 2. Best fuzzy match — score each candidate and pick the highest
    query_words = set(country_name.split())
    best_code = None
    best_score = 0
    best_name_len = float("inf")  # tiebreaker: prefer shorter official names

    for official_name, code in mapping["all"]:
        score = 0
        official_words = set(official_name.split())

        # Shared words (strongest signal)
        shared = query_words & official_words
        if shared:
            query_coverage = len(shared) / len(query_words)
            official_coverage = len(shared) / len(official_words)
            score = query_coverage * 0.7 + official_coverage * 0.3

        # Starts-with on first word ("czech" → "czechia")
        if not shared and len(country_name) >= 5:
            off_first = official_name.split()[0]
            qry_first = country_name.split()[0]
            if len(qry_first) >= 5 and (
                off_first.startswith(qry_first) or qry_first.startswith(off_first)
            ):
                score = 0.5

        # Update best: higher score wins; on tie, prefer shorter official name
        name_len = len(official_name)
        if score > best_score or (score == best_score and score > 0 and name_len < best_name_len):
            best_score = score
            best_code = code
            best_name_len = name_len

    # Require a minimum confidence
    if best_score >= 0.4:
        return best_code

    return "EU"

def _build_ryanair_url(flight: Flight, adults: int, return_flight: Flight = None):
    """
    Constructs the URL. If return_flight is provided, it's a round trip.
    Otherwise, it's a one-way trip.
    """
    d_out = flight.departure_time.strftime('%Y-%m-%d')
    orig = flight.origin
    dest = flight.destination

    params = {
        "adults": adults,
        "teens": 0, "children": 0, "infants": 0,
        "dateOut": d_out,
        "isConnectedFlight": "false",
        "discount": 0, "promoCode": "",
        "originIata": orig,
        "destinationIata": dest,
        "tpAdults": adults,
        "tpTeens": 0, "tpChildren": 0, "tpInfants": 0,
        "tpStartDate": d_out,
        "tpDiscount": 0, "tpPromoCode": "",
        "tpOriginIata": orig,
        "tpDestinationIata": dest
    }

    if return_flight:
        # Standard Round Trip
        d_in = return_flight.departure_time.strftime('%Y-%m-%d')
        params.update({
            "isReturn": "true",
            "dateIn": d_in,
            "tpEndDate": d_in
        })
    else:
        # One Way
        params.update({
            "isReturn": "false",
            "dateIn": "",
            "tpEndDate": ""
        })

    base_url = "https://www.ryanair.com/it/it/trip/flights/select"
    return f"{base_url}?{urllib.parse.urlencode(params)}"

def get_booking_links(deal: Deal) -> list[dict]:
    """
    Returns a list of button definitions: [{'label': '...', 'url': '...'}]
    """
    adults = deal.profile.adults if deal.profile.adults else 1

    # Check if standard round trip (A->B and B->A)
    is_standard = (deal.outbound.destination == deal.inbound.origin) and \
                  (deal.outbound.origin == deal.inbound.destination)

    if is_standard:
        return [{
            "label": "Book Now",
            "url": _build_ryanair_url(deal.outbound, adults, deal.inbound),
            "class": "btn-outline-success"
        }]
    else:
        # Different airports: Two separate one-way links
        return [
            {
                "label": "Book Outbound",
                "url": _build_ryanair_url(deal.outbound, adults),
                "class": "btn-outline-primary"
            },
            {
                "label": "Book Return",
                "url": _build_ryanair_url(deal.inbound, adults),
                "class": "btn-outline-secondary"
            }
        ]
