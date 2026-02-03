from datetime import date, timedelta, datetime, time
from ryanair import Ryanair
from modules import Trip, Flight
from typing import Union
import db
from config import ORIGIN_IATA, CURRENCY, WEEKS_HORIZON, BASE_DAY, STRATEGIES, LABELS_TO_TIME_RANGES, LABELS_TO_OFFSETS


def get_next_base_day(base_day: int):
    today = date.today()
    days_ahead = (base_day - today.weekday()) % 7
    days_ahead = 7 if days_ahead == 0 else days_ahead
    return today + timedelta(days=days_ahead)

def convert_to_dataclass(ryanair_trip: Trip):
    """Mappa l'oggetto grezzo della libreria ryanair-py nelle tue dataclass"""
    out = ryanair_trip.outbound
    ret = ryanair_trip.inbound
    
    f_out = Flight(
        departureTime=out.departureTime, arrivalTime=out.arrivalTime,
        flightNumber=out.flightNumber, price=out.price, currency=out.currency,
        origin=out.origin, originFull=out.originFull,
        destination=out.destination, destinationFull=out.destinationFull
    )
    
    f_in = Flight(
        departureTime=ret.departureTime, arrivalTime=ret.arrivalTime,
        flightNumber=ret.flightNumber, price=ret.price, currency=ret.currency,
        origin=ret.origin, originFull=ret.originFull,
        destination=ret.destination, destinationFull=ret.destinationFull
    )
    
    return Trip(totalPrice=ryanair_trip.totalPrice, outbound=f_out, inbound=f_in)

def run_strategy(api: Ryanair, label: str,
                 source_airport_iata: str,
                 start_date: Union[datetime, date, str],
                 day_offset_out: Union[datetime, date, str],
                 day_offset_in: Union[datetime, date, str],
                 time_out_from: Union[str, time] = "00:00",
                 time_out_to: Union[str, time] = "23:59",
                 time_in_from: Union[str, time] = "00:00",
                 time_in_to: Union[str, time] = "23:59"):
    """
    Esegue una query specifica su Ryanair e processa i risultati.
    """
    date_out = start_date + timedelta(days=day_offset_out)
    date_in = start_date + timedelta(days=day_offset_in)
    
    print(f"🔎 Strategy [{label}]: {date_out.strftime('%d/%m')} -> {date_in.strftime('%d/%m')}")

    trips_raw = api.get_cheapest_return_flights(
        source_airport=source_airport_iata,
        date_from=date_out,
        date_to=date_out, # Giorno secco
        return_date_from=date_in,
        return_date_to=date_in, # Giorno secco
        outbound_departure_time_from=time_out_from,
        outbound_departure_time_to=time_out_to,
        inbound_departure_time_from=time_in_from,
        inbound_departure_time_to=time_in_to
    )
    
    processed = 0
    for t_raw in trips_raw:
        trip = convert_to_dataclass(t_raw)
        
        if db.should_notify(trip):
            print(f"   🔔 NOTIFICA: {trip.outbound.destination} ({trip.totalPrice}€) [{label}]")
            # QUI INSERISCI LA CHIAMATA A NTFY/TELEGRAM
        processed += 1
        
    print(f"   Terminato: {processed} voli analizzati.")

def main():
    db.init()
    db.prune_old_trips()
    
    api = Ryanair(currency=CURRENCY)
    
    # Calcola i prossimi 4 weekend
    base_day = get_next_base_day(BASE_DAY)
    
    for i in range(WEEKS_HORIZON): # Prossime 4 settimane
        curr_base_day = base_day + timedelta(weeks=i)
        # ciclo sulle startegie definite
        for label in STRATEGIES:
            doo, doi = LABELS_TO_OFFSETS[label]
            (tof, tot), (tif, tit) = LABELS_TO_TIME_RANGES[label]
            run_strategy(api, label, ORIGIN_IATA, curr_base_day,
                         day_offset_out=doo,
                         day_offset_in=doi,
                         time_out_from=tof,
                         time_out_to=tot,
                         time_in_from=tif,
                         time_in_to=tit)

if __name__ == "__main__":
    main()
