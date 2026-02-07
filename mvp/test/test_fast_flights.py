from fast_flights import create_filter, get_flights_from_filter, FlightData, Passengers
import pprint

filter = create_filter(
    flight_data=[
        # Include more if it's not a one-way trip
        FlightData(
            date="2026-05-24",  # Date of departure
            from_airport="PSA",  # Departure (airport)
            to_airport="STN",  # Arrival (airport)
        ),
        FlightData(
            date="2026-05-25",  # Date of departure
            from_airport="STN",  # Departure (airport)
            to_airport="PSA",  # Arrival (airport)
        )
    ],
    # trip="round-trip",  # Trip type
    trip="one-way",  # Trip type
    passengers=Passengers(adults=1, children=0, infants_in_seat=0, infants_on_lap=0),  # Passengers
    seat="economy",  # Seat type
    max_stops=0,  # Maximum number of stops
)

# Do not construct cookies here: `get_flights_from_filter` embeds default cookies
# and will use them automatically when no cookies are provided.
pprint.pprint(get_flights_from_filter(filter, mode="local"))

# <div class="JMc5Xc" jsaction="click:O1htCb" tabindex="0" role="link"
#     aria-label="From 118 euros round trip total.This price does not include overhead bin access. Nonstop flight with Ryanair. Operated by Malta Air. Leaves Pisa International Airport at 6:05 AM on Saturday, May 23 and arrives at London Stansted Airport at 7:25 AM on Saturday, May 23. Total duration 2 hr 20 min.  Select flight">
# </div>

# /m/02j71
