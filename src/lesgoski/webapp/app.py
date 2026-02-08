# webapp/app.py
import csv
import json
import logging
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from lesgoski.webapp.utils import get_country_code, get_booking_links
from lesgoski.services.airports import get_nearby_set
from fastapi import FastAPI, Depends, Request, Form, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from lesgoski.database.engine import get_db, init_db, SessionLocal
from lesgoski.database.models import Deal, SearchProfile
from lesgoski.core.schemas import StrategyConfig
from lesgoski.services.orchestrator import update_single_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

_WEBAPP_DIR = Path(__file__).parent

# Ensure DB tables exist
init_db()
app = FastAPI()
app.mount("/static", StaticFiles(directory=str(_WEBAPP_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(_WEBAPP_DIR / "templates"))
templates.env.globals.update(booking_links=get_booking_links)

@lru_cache(maxsize=1)
def _load_airports() -> list[dict]:
    """Load airport data from CSV, keeping only essential fields."""
    csv_path = _WEBAPP_DIR / "data" / "filtered_airports.csv"
    airports = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            iata = row.get("iata_code", "").strip()
            if not iata:
                continue
            airports.append({
                "iata": iata,
                "name": row.get("name", "").strip(),
                "city": row.get("municipality", "").strip(),
                "country": row.get("iso_country", "").strip(),
            })
    return airports

def run_background_update(profile_id: int):
    db = SessionLocal()
    try:
        update_single_profile(db, profile_id)
    except Exception as e:
        logger.error(f"Background update failed: {e}", exc_info=True)
    finally:
        db.close()

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
def view_deals(request: Request, profile_id: int = None, db: Session = Depends(get_db)):
    all_profiles = db.query(SearchProfile).filter(SearchProfile.is_active == True).all()

    # Logic: No profiles -> Go to create
    if not all_profiles:
        return RedirectResponse("/profile/new", status_code=303)

    # Logic: No specific profile requested -> Load first
    current_profile = None
    if profile_id:
        current_profile = db.get(SearchProfile,profile_id)

    if not current_profile:
        # Fallback to the first one available
        return RedirectResponse(f"/?profile_id={all_profiles[0].id}", status_code=303)

    # Fetch deals for this profile
    deals = db.query(Deal).options(
        joinedload(Deal.outbound),
        joinedload(Deal.inbound),
        joinedload(Deal.profile)
    ).filter(Deal.profile_id == current_profile.id).all()

    # Grouping Data — metro-area aware
    # Each deal appears in all nearby airport groups so that e.g.
    # a PSA→GRO / BCN→PSA deal shows up under both GRO and BCN.
    grouped = defaultdict(list)
    unique_countries = set()
    unique_destinations = set()
    # Cache full names: first encountered full_name wins for each code
    dest_full_names: dict[str, str] = {}

    for deal in deals:
        if not deal.outbound:
            continue

        out_dest = deal.outbound.destination
        in_origin = deal.inbound.origin if deal.inbound else out_dest

        # All airports in the metro area of the destination side
        area_codes = get_nearby_set(out_dest) | get_nearby_set(in_origin)

        # Only keep codes that actually appear as outbound destinations
        # in this profile's deals (avoid phantom groups for airports
        # we have no flights to)
        for code in area_codes:
            grouped[code].append(deal)

        # Track full names for the actual airports in this deal
        for code, full_name in [
            (out_dest, deal.outbound.destination_full or out_dest),
            (in_origin, (deal.inbound.origin_full if deal.inbound else None) or in_origin),
        ]:
            if code not in dest_full_names:
                dest_full_names[code] = full_name
            country_code = get_country_code(full_name)
            unique_countries.add(country_code)
            unique_destinations.add(code)

    # Only show groups that have at least one deal with a direct flight
    # to/from that airport (avoid empty groups for nearby-only codes)
    direct_codes = set()
    for deal in deals:
        if deal.outbound:
            direct_codes.add(deal.outbound.destination)
        if deal.inbound:
            direct_codes.add(deal.inbound.origin)

    view_data = []
    for dest_code, deal_list in grouped.items():
        if not deal_list:
            continue
        if dest_code not in direct_codes:
            continue

        # Deduplicate (a deal can be added multiple times via area_codes)
        seen_ids = set()
        unique_deals = []
        for d in deal_list:
            if d.id not in seen_ids:
                seen_ids.add(d.id)
                unique_deals.append(d)
        unique_deals.sort(key=lambda x: x.total_price_pp)

        first = unique_deals[0]
        full_name = dest_full_names.get(dest_code, dest_code)
        country_code = get_country_code(full_name)

        view_data.append({
            "destination_code": dest_code,
            "destination_name": full_name.split(',')[0].strip(),
            "country_code": country_code,
            "country_flag": f"https://flagsapi.com/{country_code.upper()}/shiny/64.png",
            "best_deal": first,
            "other_deals": unique_deals[1:]
        })

    view_data.sort(key=lambda x: x["best_deal"].total_price_pp)

    return templates.TemplateResponse("deals.html", {
        "request": request,
        "destinations": view_data,
        "current_profile": current_profile,
        "all_profiles": all_profiles,
        "filter_countries": sorted(list(unique_countries)),
        "filter_destinations": sorted(list(unique_destinations)),
        "notify_destinations": current_profile.notify_destinations if current_profile else [],
    })

@app.get("/profile/new", response_class=HTMLResponse)
def new_profile_form(request: Request):
    return templates.TemplateResponse("profile_form.html", {
        "request": request, "profile": None, "is_new": True
    })

@app.get("/profile/{pid}", response_class=HTMLResponse)
def edit_profile_form(request: Request, pid: int, db: Session = Depends(get_db)):
    profile = db.get(SearchProfile,pid)
    return templates.TemplateResponse("profile_form.html", {
        "request": request, "profile": profile, "is_new": False
    })

@app.post("/profile/save")
async def save_profile(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    profile_id: int = Form(None),
    name: str = Form(...),
    origins: str = Form(...),
    allowed_destinations: str = Form(""),
    max_price: float = Form(...),
    adults: int = Form(...),
    strategy_json: str = Form(...)
):
    # Parse & Validate
    origin_list = [o.strip().upper() for o in origins.split(',') if o.strip()]
    if not origin_list:
        return HTMLResponse("At least one origin airport is required.", status_code=400)
    dest_list = [d.strip().upper() for d in allowed_destinations.split(',') if d.strip()]
    try:
        strategy_dict = json.loads(strategy_json)
        StrategyConfig(**strategy_dict)
    except Exception as e:
        return HTMLResponse(f"Invalid Strategy JSON: {e}", status_code=400)

    if profile_id:
        profile = db.get(SearchProfile,profile_id)
    else:
        profile = SearchProfile()
        db.add(profile)

    profile.name = name
    profile.origins = origin_list
    profile.allowed_destinations = dest_list
    profile.max_price = max_price
    profile.adults = adults
    profile._strategy_object = strategy_json

    db.commit()
    db.refresh(profile)

    # TRIGGER IMMEDIATE UPDATE
    background_tasks.add_task(run_background_update, profile.id)

    return RedirectResponse(f"/?profile_id={profile.id}", status_code=303)

@app.post("/update/{profile_id}")
def trigger_manual_update(profile_id: int):
    try:
        run_background_update(profile_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Manual update failed: {e}", exc_info=True)
        return HTMLResponse(content=f"Update failed: {e}", status_code=500)

@app.post("/profile/{pid}/delete")
def delete_profile(pid: int, db: Session = Depends(get_db)):
    profile = db.get(SearchProfile, pid)
    if profile:
        profile.is_active = False
        db.commit()
    return RedirectResponse("/", status_code=303)

@app.get("/api/airports")
def get_airports():
    return _load_airports()

@app.post("/api/notify-toggle")
async def toggle_notify_destination(
    request: Request,
    db: Session = Depends(get_db),
):
    """Toggle immediate notifications for a specific destination."""
    body = await request.json()
    profile_id = body.get("profile_id")
    destination = body.get("destination")

    if not profile_id or not destination:
        return {"error": "profile_id and destination required"}

    profile = db.get(SearchProfile, int(profile_id))
    if not profile:
        return {"error": "Profile not found"}

    current = profile.notify_destinations
    if destination in current:
        current.remove(destination)
        enabled = False
    else:
        current.append(destination)
        enabled = True

    profile.notify_destinations = current
    db.commit()

    return {"destination": destination, "enabled": enabled}


def main():
    """Entry point for the web application."""
    import uvicorn
    uvicorn.run(
        "lesgoski.webapp.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
