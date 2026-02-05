# mvp_gemini/webapp/main.py
from fastapi import FastAPI, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, joinedload
from database.db import get_db
from database.models import Deal, Flight
from collections import defaultdict
import urllib.parse

app = FastAPI()

templates = Jinja2Templates(directory="webapp/templates")

# --- HELPER FUNCTIONS ---

def get_country_code(full_name: str) -> str:
    if not full_name: return "EU"
    country_name = full_name.split(',')[-1].strip().lower()
    mapping = {
        "italy": "IT", "united kingdom": "GB", "spain": "ES", 
        "france": "FR", "germany": "DE", "ireland": "IE", 
        "portugal": "PT", "belgium": "BE", "netherlands": "NL",
        "poland": "PL", "greece": "GR", "hungary": "HU",
        "austria": "AT", "czech republic": "CZ", "switzerland": "CH",
        "morocco": "MA", "malta": "MT", "croatia": "HR", "denmark": "DK",
        "sweden": "SE", "norway": "NO", "finland": "FI", "lithuania": "LT",
        "latvia": "LV", "estonia": "EE", "slovakia": "SK", "slovenia": "SI",
        "bulgaria": "BG", "romania": "RO", "cyprus": "CY", "luxembourg": "LU",
        "serbia": "RS", "bosnia and herzegovina": "BA", "north macedonia": "MK",
        "albania": "AL", "montenegro": "ME", "ukraine": "UA", "belarus": "BY",
        "turkey": "TR", "russia": "RU",
    }
    return mapping.get(country_name, "EU")

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
            "class": "btn-light" 
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

# Register helper
templates.env.globals.update(booking_links=get_booking_links)


# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
def view_deals(request: Request, db: Session = Depends(get_db)):
    deals = db.query(Deal).options(
        joinedload(Deal.outbound),
        joinedload(Deal.inbound),
        joinedload(Deal.profile)
    ).all()

    # Extract Profile Name (assuming single profile usage for MVP)
    profile_name = "Deals"
    if deals:
        profile_name = deals[0].profile.name

    grouped = defaultdict(list)
    for deal in deals:
        if deal.outbound:
            grouped[deal.outbound.destination].append(deal)

    view_data = []
    for dest_code, deal_list in grouped.items():
        if not deal_list: continue
        
        deal_list.sort(key=lambda x: x.total_price_pp)
        first = deal_list[0]
        
        full_name = first.outbound.destination_full or dest_code
        city_airport = full_name.split(',')[0].strip()
        country_code = get_country_code(full_name)

        view_data.append({
            "destination_code": dest_code,
            "destination_name": city_airport,
            "country_flag": f"https://flagsapi.com/{country_code.upper()}/flat/64.png",
            "best_deal": first,
            "other_deals": deal_list[1:]
        })
    
    view_data.sort(key=lambda x: x["best_deal"].total_price_pp)

    return templates.TemplateResponse("deals.html", {
        "request": request, 
        "destinations": view_data,
        "profile_name": profile_name
    })
