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


def plane_speed(distance: float) -> float:
    # obtained from linearly interpolating the data from two points:
    # (722,  395) -- SGN to HAN
    # (5445, 551) -- LAX to NRT
    return 0.033029853906415 * distance + 371.15244547957


def layover_score(leg: Leg) -> float:
    """
    Estimates a score that indicates how much layover we could get from the
    given leg.
    """

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
    flight_time = flight_distance / plane_speed(flight_distance)  # hours

    # The API only gives us the total duration of the entire trip, which
    # includes layovers.
    total_duration = (leg.arrival - leg.departure).total_seconds() / 3600  # hours
    return total_duration - flight_time


def remove_invalid_flights(flights: list[Flight]) -> list[Flight]:
    to_delete = []

    for flight in flights:
        if flight.legs is None:
            to_delete.append(flight)
            continue

        for leg in flight.legs:
            if leg.stops is None or len(leg.stops) == 0:
                to_delete.append(flight)
                continue

    for flight in to_delete:
        flights.remove(flight)

    return flights


def calculate_layover_scores(flights: list[Flight]) -> list[Flight]:
    """
    Calculates the layover scores for each flight in the given parsed response.
    """
    for flight in flights:
        assert flight.legs is not None

        total_score = 0
        for leg in flight.legs:
            leg.layover_hours = layover_score(leg)
            total_score += leg.layover_hours
        flight.layover_hours = total_score / len(flight.legs)

    return flights
