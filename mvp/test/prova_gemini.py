import tls_client
from typing import Union
from datetime import timedelta, date, datetime
from urllib.parse import urlencode


def next_friday(from_date=None):
    if from_date is None:
        from_date = date.today()

    days_ahead = (4 - from_date.weekday()) % 7
    days_ahead = 7 if days_ahead == 0 else days_ahead
    return from_date + timedelta(days=days_ahead)

def _format_date_for_api(d: Union[datetime, date, str]):
        if isinstance(d, str):
            return d

        if isinstance(d, datetime):
            return d.date().isoformat()

        if isinstance(d, date):
            return d.isoformat()

# Configura un client che finge di essere Chrome
session = tls_client.Session(
    client_identifier="chrome_112",
    random_tls_extension_order=True
)

def scan_prices(origin: str, destination: str = '', start_date: Union[datetime, date, str] = None):
    """
    Cerca voli. 
    Se destination è 'ANY', usa l'API 'oneWayFares' che cerca ovunque.
    Se destination è specifica, filtra i risultati.
    """
    url = "https://services-api.ryanair.com/farfnd/3/oneWayFares"
    
    if start_date is None:
        start_date = next_friday()
    start_date = _format_date_for_api(start_date)
    print(start_date)
    
    params = {
        "departureAirportIataCode": origin,
        "arrivalAirportIataCode": destination,
        "language": "en",
        "limit": 100, 
        "market": "it",
        "outboundDepartureDateFrom": start_date,
        "outboundDepartureDateTo": start_date,
    }

    try:
        full_url = f"{url}?{urlencode(params)}"
        print("REQUEST:", full_url)

        resp = session.get(url, params=params)
        data = resp.json()
        
        results = []
        if "fares" in data:
            for item in data["fares"]:
                out = item["outbound"]
                res = {
                    "origin": origin,
                    "dest": out["arrivalAirport"]["iataCode"],
                    "city": out["arrivalAirport"]["name"],
                    "date": out["departureDate"].split("T")[0],
                    "price": out["price"]["value"],
                    "currency": out["price"]["currencyCode"],
                    "flight_key": f"{origin}_{out['arrivalAirport']['iataCode']}_{out['departureDate']}"
                }
                results.append(res)
        return results

    except Exception as e:
        print(f"Errore API Ryanair: {e}")
        return []

if __name__ == "__main__":
    flights = scan_prices("PSA", "KRK")
    for f in flights:
        print(f)