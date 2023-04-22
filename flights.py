import math

import airports
from models import *

# function getDistanceFromLatLonInKm(lat1,lon1,lat2,lon2) {
#   var R = 6371; // Radius of the earth in km
#   var dLat = deg2rad(lat2-lat1);  // deg2rad below
#   var dLon = deg2rad(lon2-lon1);
#   var a =
#     Math.sin(dLat/2) * Math.sin(dLat/2) +
#     Math.cos(deg2rad(lat1)) * Math.cos(deg2rad(lat2)) *
#     Math.sin(dLon/2) * Math.sin(dLon/2)
#     ;
#   var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
#   var d = R * c; // Distance in km
#   return d;
# }


def deg2rad(deg: float) -> float:
    return deg * (math.pi / 180)


def calculate_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """
    Calculates the distance from the origin to a point on the Earth's surface
    using the Haversine formula.

    For reference, see https://stackoverflow.com/a/27943/5041327.
    """
    lat1, lon1 = p1
    lat2, lon2 = p2
    R = 6371  # Radius of the earth in km
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat / 2) * math.sin(dLat / 2)) + (
        math.cos(deg2rad(lat1))
        * math.cos(deg2rad(lat2))
        * math.sin(dLon / 2)
        * math.sin(dLon / 2)
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    d = R * c
    return d


def layover_score(leg: Leg) -> float:
    """
    Estimates a score that indicates how much layover we could get from the
    given leg.
    """

    # Use a constant plane speed. This doesn't matter too much, since we can
    # expect overseas flights to be long enough that we're flying at a high
    # velocity. Also, this score is meant to be relative.
    PLANE_SPEED = 900  # km/h

    flight_distance = 0
    stops = [
        leg.origin,
        *(leg.stops if leg.stops is not None else []),
        leg.destination,
    ]

    for i in range(len(stops) - 1):
        stop1 = stops[i]
        stop2 = stops[i + 1]

        try:
            assert stop1 is not None
            assert stop2 is not None
            assert stop1.display_code is not None
            assert stop2.display_code is not None
        except:
            continue

        stop1_airport = airports.get_by_iata(stop1.display_code)
        stop2_airport = airports.get_by_iata(stop2.display_code)

        flight_distance += calculate_distance(
            (stop1_airport.lat, stop1_airport.long),
            (stop2_airport.lat, stop2_airport.long),
        )

    # Estimate just the time it takes to fly in-between airports.
    estimated_flight_time = flight_distance / PLANE_SPEED

    # The API only gives us the total duration of the entire trip, which
    # includes layovers.
    total_duration = (leg.arrival - leg.departure).total_seconds()
    # We'll compare the total trip duration with just the flight time, and this
    # will give us a layover score: the longer the layover, the bigger the
    # difference is.
    estimated_total_time = total_duration / PLANE_SPEED

    return estimated_total_time - estimated_flight_time
