from datetime import timedelta, date
from ryanair import Ryanair


def next_friday(from_date=None):
    if from_date is None:
        from_date = date.today()

    days_ahead = (4 - from_date.weekday()) % 7
    days_ahead = 7 if days_ahead == 0 else days_ahead
    return from_date + timedelta(days=days_ahead)

api = Ryanair(currency="EUR")  # Euro currency, so could also be GBP etc. also

query = {
	'source_airport': 'PSA',
    'date_from': next_friday(),
	'date_to': next_friday() + timedelta(days=30.),
	'return_date_from': next_friday() + timedelta(days=1.),
	'return_date_to': next_friday() + timedelta(days=31.),
}

trips = api.get_cheapest_return_flights(**query)

# print
print(f"Found {len(trips)} results for the given search:")
for trip in sorted(trips, key=lambda t: (t.outbound.destination, t.outbound.departureTime)):
    print(
        f"{trip.outbound.flightNumber} | "
        f"{trip.outbound.origin}->{trip.outbound.destination} | "
        f"{trip.outbound.departureTime:%Y-%m-%d %H:%M} | "
        f"{trip.outbound.arrivalTime:%Y-%m-%d %H:%M} | "
        f"{trip.inbound.flightNumber} | "
        f"{trip.inbound.origin}->{trip.inbound.destination} | "
        f"{trip.inbound.departureTime:%Y-%m-%d %H:%M} | "
        f"{trip.inbound.arrivalTime:%Y-%m-%d %H:%M} | "
        f"{trip.totalPrice:.2f} {trip.outbound.currency}"
    )
