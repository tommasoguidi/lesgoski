# services/airports.py
"""
Metro-area airport grouping.

Provides utilities to find airports near a given airport, so that
the matcher can treat e.g. GRO and BCN as the same destination area,
and the scanner can fetch return legs from nearby alternatives.
"""

import csv
import math
import logging
from functools import lru_cache
from pathlib import Path
from lesgoski.config import NEARBY_AIRPORT_RADIUS_KM

logger = logging.getLogger(__name__)

_CSV_PATH = Path(__file__).resolve().parent.parent / "webapp" / "data" / "filtered_airports.csv"


@lru_cache(maxsize=1)
def _load_airport_coords() -> dict[str, tuple[float, float]]:
    """Load {IATA: (lat, lon)} from the airports CSV."""
    coords: dict[str, tuple[float, float]] = {}
    with open(_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            iata = (row.get("iata_code") or "").strip()
            if not iata:
                continue
            try:
                lat = float(row["latitude_deg"])
                lon = float(row["longitude_deg"])
                coords[iata] = (lat, lon)
            except (ValueError, KeyError):
                continue
    return coords


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in km."""
    R = 6371.0
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_nearby_airports(iata: str, radius_km: float | None = None) -> list[str]:
    """
    Return all IATA codes within `radius_km` of the given airport,
    INCLUDING the airport itself.

    Example: get_nearby_airports('GRO', 100) → ['GRO', 'BCN', 'REU']

    Used by the matcher to relax the destination match and by the scanner
    to know which airports to fetch return legs from.
    """
    if radius_km is None:
        radius_km = NEARBY_AIRPORT_RADIUS_KM

    coords = _load_airport_coords()
    if iata not in coords:
        logger.warning(f"Airport {iata} not found in CSV — returning only itself")
        return [iata]

    if radius_km <= 0:
        return [iata]

    h_lat, h_lon = coords[iata]
    nearby = [iata]

    for other, (lat, lon) in coords.items():
        if other == iata:
            continue
        if _haversine_km(h_lat, h_lon, lat, lon) <= radius_km:
            nearby.append(other)

    return nearby


@lru_cache(maxsize=256)
def get_nearby_set(iata: str, radius_km: float | None = None) -> frozenset[str]:
    """Cached frozenset version of get_nearby_airports — used by the matcher."""
    return frozenset(get_nearby_airports(iata, radius_km))


def are_nearby(iata_a: str, iata_b: str, radius_km: float | None = None) -> bool:
    """Check if two airports are within the metro-area radius of each other."""
    if iata_a == iata_b:
        return True
    return iata_b in get_nearby_set(iata_a, radius_km)
