import os
import math
import json
import tempfile
from typing import cast
from datetime import date as Date

from fastapi import HTTPException
from pyrate_limiter import RequestRate, Limiter, Duration, SQLiteBucket

import limiter
import httputil
import airports
from models import *

from dotenv import load_dotenv

load_dotenv()


RAPID_API_HOST = "skyscanner50.p.rapidapi.com"
RAPID_API_URL = "https://" + RAPID_API_HOST + "/api/v1"
RAPID_API_HEADERS = {
    "X-RapidAPI-Key": os.getenv("RAPID_API_KEY"),
    "X-RapidAPI-Host": RAPID_API_HOST,
}


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
        assert stop1_airport is not None
        assert stop2_airport is not None

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
        if flight in flights:
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


# 5000/1mo
rapid_api_limiter = limiter.new(RequestRate(5000, Duration.MONTH))

fetch_flights_limiter = limiter.new(RequestRate(10, Duration.SECOND))
fetch_flights_user_limiter = limiter.new(RequestRate(5, 30 * Duration.SECOND))

fetch_details_limiter = limiter.new(RequestRate(4, Duration.SECOND))
fetch_details_user_limiter = limiter.new(RequestRate(10, 30 * Duration.SECOND))


@rapid_api_limiter.ratelimit()
async def fetch_flight_details(
    itineraryId: str,
    origin: str,
    dest: str,
    date: Date,
    return_date: Date,
    num_adults: int,
    user_id: str,  # used for user-specific rate limiting
) -> FlightDetailResponse:
    await limiter.wait(
        lambda: rapid_api_limiter.ratelimit(),
        lambda: fetch_details_limiter.ratelimit(delay=True),
        lambda: fetch_details_user_limiter.ratelimit(user_id, delay=True),
    )

    res = await httputil.client.get(
        RAPID_API_URL + "/getFlightDetails",
        headers=RAPID_API_HEADERS,
        params={
            "itineraryId": itineraryId,
            "legs": json.dumps(
                [
                    {"origin": origin, "destination": dest, "date": str(date)},
                    {"origin": dest, "destination": origin, "date": str(return_date)},
                ]
            ),
            "adults": num_adults,
            "currency": "USD",
            "countryCode": "US",
            "market": "en-US",
        },
    )

    text = await res.text()

    try:
        data = FlightDetailResponse.parse_raw(text)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed to parse response: {e}"
                if res.ok
                else f"Server returned HTTP {res.status}"
            ),
        )

    return data


@rapid_api_limiter.ratelimit()
async def fetch_flights(
    origin: str,
    dest: str,
    date: Date,
    return_date: Date,
    num_adults: int,
    wait_time: int,
    user_id: str,  # used for user-specific rate limiting
) -> FlightApiResponse:
    await limiter.wait(
        lambda: rapid_api_limiter.ratelimit(),
        lambda: fetch_flights_limiter.ratelimit(delay=True),
        lambda: fetch_flights_user_limiter.ratelimit(user_id, delay=True),
    )

    print(RAPID_API_HEADERS)
    res = await httputil.client.get(
        RAPID_API_URL + "/searchFlights",
        headers=RAPID_API_HEADERS,
        params={
            "origin": origin,
            "destination": dest,
            "date": str(date),
            "returnDate": str(return_date),
            "waitTime": wait_time,
            "adults": num_adults,
            "currency": "USD",
            "countryCode": "US",
            "market": "en-US",
        },
    )

    try:
        data = FlightApiResponse.parse_raw(await res.text())
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed to parse response: {e}"
                if res.ok
                else f"Server returned HTTP {res.status}"
            ),
        )

    if data is None or data.data is None:
        raise HTTPException(status_code=404, detail="No flights found")

    data.data = remove_invalid_flights(data.data)
    data.data = calculate_layover_scores(data.data)

    data.data.sort(
        # Shut Pyright up.
        key=lambda flight: cast(float, flight.layover_hours),
        reverse=True,
    )

    return data
