import json
import asyncio
import os
import base64
import bcrypt
import time
from typing import cast

from dotenv import load_dotenv
from requests import request
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from snowflake import SnowflakeGenerator

from airports import (
    find_by_name as find_airports_by_name,
    find_by_coords as find_airports_by_coords,
)
import flights

from db import db
from deps import get_authorized_user
from models import *

load_dotenv()

MAX_WAIT = 5000
MIN_WAIT = 500

RAPID_API_HOST = "skyscanner50.p.rapidapi.com"
RAPID_API_URL = "https://" + RAPID_API_HOST + "/api/v1"
RAPID_API_HEADERS = {
    "X-RapidAPI-Key": os.getenv("RAPID_API_KEY"),
    "X-RapidAPI-Host": RAPID_API_HOST,
}

TOKEN_EXPIRY = 604800  # 1 week


app = FastAPI(
    docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json"
)
id_generator = SnowflakeGenerator(0)


@app.get("/api/ping")
def ping():
    return "Pong!!!"


@app.post("/api/login")
def login(request: LoginRequest) -> LoginResponse:
    cur = db.cursor()
    res = cur.execute(
        "SELECT id, passhash, first_name, profile_picture FROM users WHERE email = ?",
        (request.email,),
    )

    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=401)

    if not bcrypt.checkpw(request.password.encode(), row[1].encode()):
        raise HTTPException(status_code=401)

    token = base64.b64encode(os.urandom(32)).decode()
    expire = int(time.time()) + TOKEN_EXPIRY

    cur.execute(
        "INSERT INTO sessions (token, user_id, expiration) VALUES (?, ?, ?)",
        (token, row[0], expire),
    )
    db.commit()

    return LoginResponse(
        id=row[0],
        first_name=row[2],
        profile_picture=row[3],
        token=token,
        expiry=expire,
    )


@app.post("/api/register", status_code=204)
def register(request: RegisterRequest):
    id = str(next(id_generator))
    passhash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()

    cur = db.cursor()
    cur.execute(
        "INSERT INTO users (id, email, first_name, passhash) VALUES (?, ?, ?, ?)",
        (id, request.email, request.first_name, passhash),
    )
    db.commit()


@app.get("/api/me")
def me(user: AuthorizedUser = Depends(get_authorized_user)) -> UserResponse:
    cur = db.cursor()
    res = cur.execute(
        "SELECT id, email, first_name, profile_picture FROM users WHERE id = ?",
        (user.id,),
    )
    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=500)

    return UserResponse(**row)

@app.get("/api/user")
def me(id: str) -> UserResponse:
    cur = db.cursor()
    res = cur.execute(
        "SELECT id, email, first_name, profile_picture FROM users WHERE id = ?",
        (id,),
    )
    row = res.fetchone()
    print(row)
    if row is None:
        raise HTTPException(status_code=404)

    return UserResponse(**row)


def get_flight_details(
    itineraryId: str,
    date: str,
    return_date: str | None,
    origin: str,
    num_adults: int | None,
    dest: str,
) -> FlightDetailResponse:
    res = request(
        "GET",
        RAPID_API_URL + "/getFlightDetails",
        headers=RAPID_API_HEADERS,
        params={
            "itineraryId": itineraryId,
            "legs": json.dumps(
                [
                    {"origin": origin, "destination": dest, "date": date},
                    {"origin": dest, "destination": origin, "date": return_date},
                ]
            ),
            "adults": num_adults,
            "currency": "USD",
            "countryCode": "US",
            "market": "en-US",
        },
    )

    return FlightDetailResponse.parse_raw(res.text)


@app.get("/api/flights")
async def get_flights(
    origin: str = Query(description="3-letter airport code (IATA)"),
    dest: str = Query(description="3-letter airport code (IATA)"),
    date: str = Query(description="date of first flight in YYYYMMDD format"),
    return_date: str
    | None = Query(None, description="date of the returning flight in YYYYMMDD format"),
    num_adults: int | None = Query(1, description="number of adults"),
    wait_time: int | None = Query(None, description="max wait time in minutes"),
    page: int = Query(1, description="page number"),
) -> list[FlightDetailResponse]:
    # TODO: implement eviction for old cached flights
    resp: FlightApiResponse
    PAGE_SIZE = 5

    cur = db.cursor()
    res = cur.execute(
        "SELECT response FROM flight_responses WHERE date = ? AND origin = ? AND destination = ?",
        (date, origin, dest),
    )

    row = res.fetchone()
    if row is not None:
        resp = FlightApiResponse.parse_raw(row[0])
    else:
        query_string = {
            "origin": origin,
            "destination": dest,
            "date": date,
            "returnDate": return_date,
            "waitTime": min(wait_time, MAX_WAIT) if wait_time is not None else MIN_WAIT,
            "adults": num_adults,
            "currency": "USD",
            "countryCode": "US",
            "market": "en-US",
        }

        res = request(
            "GET",
            RAPID_API_URL + "/searchFlights",
            headers=RAPID_API_HEADERS,
            params=query_string,
        )

        parsed_res = FlightApiResponse.parse_raw(res.text)
        if parsed_res is None or parsed_res.data is None:
            raise HTTPException(status_code=404, detail="No flights found")

        to_delete = []

        for flight in parsed_res.data:
            if flight.legs is None:
                to_delete.append(flight)
                continue

            for leg in flight.legs:
                if leg.stops is None or len(leg.stops) == 0:
                    to_delete.append(flight)
                    continue

        for flight in to_delete:
            parsed_res.data.remove(flight)

        for flight in parsed_res.data:
            assert flight.legs is not None

            total_score = 0
            for leg in flight.legs:
                leg.layover_hours = flights.layover_score(leg)
                total_score += leg.layover_hours
            flight.layover_hours = total_score / len(flight.legs)

        parsed_res.data.sort(
            # Shut Pyright up.
            key=lambda flight: cast(float, flight.layover_hours),
            reverse=True,
        )

        resp = parsed_res

        cur.execute(
            """
                INSERT INTO flight_responses (date, origin, destination, timestamp, response)
                    VALUES (?, ?, ?, ?, ?)
            """,
            (
                date,
                origin,
                dest,
                resp.timestamp or int(time.time() * 1000),
                resp.json(),
            ),
        )
        db.commit()

    if resp.data is None:
        return []

    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    resp.data = resp.data[start:end]

    details: list[FlightDetailResponse | None] = [None] * len(resp.data)

    async def loop(i):
        assert resp.data is not None
        details[i] = get_flight_details(
            itineraryId=resp.data[i].id,
            date=date,
            return_date=return_date,
            num_adults=num_adults,
            origin=origin,
            dest=dest,
        )

    coros = [loop(i) for i in range(len(resp.data))]
    await asyncio.gather(*coros)

    return cast(list[FlightDetailResponse], details)


@app.get("/api/airports")
def airports(
    name: str = Query(None, description="airport name (must not have lat or long)"),
    lat: float = Query(None, description="latitude (must also have long)"),
    long: float = Query(None, description="longitude (must also have lat)"),
) -> ListAirportsResponse:
    if name:
        airports = find_airports_by_name(name)
    elif lat and long:
        airports = find_airports_by_coords(lat, long)
    else:
        raise HTTPException(status_code=400, detail="need either ?name or ?lat&long")

    return ListAirportsResponse(airports=airports)
