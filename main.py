from datetime import timedelta, date as Date
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
from aiohttp import ClientSession

import httpcache
from db import db
from deps import get_authorized_user
from models import *
from flights import remove_invalid_flights, calculate_layover_scores
from layovers import set_popularity_for_flights, get_users_in_layover
from airports import (
    find_by_name as find_airports_by_name,
    find_by_coords as find_airports_by_coords,
    get_by_iata as get_airport_by_iata,
)

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
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
httpclient = ClientSession()
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


@app.get("/api/user/{id}")
def get_user(id: str) -> UserResponse:
    cur = db.cursor()
    res = cur.execute(
        "SELECT id, email, first_name, profile_picture FROM users WHERE id = ?",
        (id,),
    )
    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=404)

    return UserResponse(**row)


async def get_flight_details(
    itineraryId: str,
    date: str,
    return_date: str | None,
    origin: str,
    num_adults: int | None,
    dest: str,
) -> FlightDetailResponse:
    res = await httpclient.get(
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

    data = await res.text()
    return FlightDetailResponse.parse_raw(data)


@app.get("/api/flights")
async def get_flights(
    origin: str = Query(description="3-letter airport code (IATA)"),
    dest: str = Query(description="3-letter airport code (IATA)"),
    date: str = Query(description="date of first flight in YYYY-MM-DD format"),
    return_date: str = Query(
        description="date of the returning flight in YYYY-MM-DD format"
    ),
    num_adults: int | None = Query(1, description="number of adults"),
    wait_time: int | None = Query(None, description="max wait time in milliseconds"),
    page: int = Query(1, description="page number"),
) -> list[FlightDetailResponse]:
    # TODO: implement eviction for old cached flights
    resp: FlightApiResponse
    PAGE_SIZE = 5

    async def fetchSearch() -> str:
        res = await httpclient.get(
            RAPID_API_URL + "/searchFlights",
            headers=RAPID_API_HEADERS,
            params={
                "origin": origin,
                "destination": dest,
                "date": date,
                "returnDate": return_date,
                "waitTime": min(wait_time, MAX_WAIT)
                if wait_time is not None
                else MIN_WAIT,
                "adults": num_adults,
                "currency": "USD",
                "countryCode": "US",
                "market": "en-US",
            },
        )

        data = FlightApiResponse.parse_raw(await res.text())
        if data is None or data.data is None:
            raise HTTPException(status_code=404, detail="No flights found")

        data.data = remove_invalid_flights(data.data)
        data.data = calculate_layover_scores(data.data)

        data.data.sort(
            # Shut Pyright up.
            key=lambda flight: cast(float, flight.layover_hours),
            reverse=True,
        )

        return data.json()

    search_cache_key = {
        "origin": origin,
        "dest": dest,
        "date": date,
        "return_date": return_date,
    }

    if (search_data := httpcache.get(search_cache_key)) is None:
        search_data = await fetchSearch()
        httpcache.set(search_cache_key, search_data)

    search = FlightApiResponse.parse_raw(search_data)
    if search is None or search.data is None:
        raise HTTPException(status_code=404, detail="No flights found")

    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    search.data = search.data[start:end]

    details: list[FlightDetailResponse | None] = [None] * len(search.data)

    async def loop(i):
        assert search.data is not None

        cacheKey = {
            "itineraryId": search.data[i].id,
            "origin": origin,
            "dest": dest,
            "date": date,
            "return_date": return_date,
        }

        if (cache := httpcache.get(cacheKey)) is not None:
            details[i] = FlightDetailResponse.parse_raw(cache)
            return

        res = await get_flight_details(
            itineraryId=search.data[i].id,
            origin=origin,
            dest=dest,
            date=date,
            return_date=return_date,
            num_adults=num_adults,
        )

        httpcache.set(cacheKey, res.json())
        details[i] = res

    coros = [loop(i) for i in range(len(search.data))]
    await asyncio.gather(*coros)

    details_pop = cast(list[FlightDetailResponse], details)
    set_popularity_for_flights(details_pop)

    return details_pop


@app.get("/api/layovers")
def layovers(
    user: AuthorizedUser = Depends(get_authorized_user),
) -> LayoversResponse:
    """
    Get all of the current user's interested layover flights.
    """
    cur = db.cursor()
    res = cur.execute(
        "SELECT iata_code, arrive, depart FROM layovers WHERE user_id = ?",
        (user.id,),
    )

    layovers: list[LayoversResponse.Layover] = []

    rows = res.fetchall()
    for row in rows:
        airport = get_airport_by_iata(row[0])
        if airport is None:
            continue

        layovers.append(
            LayoversResponse.Layover(
                iata=row[0],
                airport=airport,
                arrive=row[1],
                depart=row[2],
            )
        )

    return LayoversResponse(layovers=layovers)


@app.post("/api/layovers", status_code=204)
def add_layover(
    body: AddOrRemoveLayoverRequest,
    user: AuthorizedUser = Depends(get_authorized_user),
):
    """
    Mark a layover flight as interested. This contributes towards a popularity
    score for each airport.
    """
    if get_airport_by_iata(body.iata) is None:
        raise HTTPException(status_code=404, detail="Airport not found")

    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO layovers (iata_code, depart, arrive, user_id)
        VALUES (?, ?, ?, ?)
        """,
        (body.iata, body.depart, body.arrive, user.id),
    )
    db.commit()


@app.delete("/api/layovers", status_code=204)
def remove_layover(
    body: AddOrRemoveLayoverRequest,
    user: AuthorizedUser = Depends(get_authorized_user),
):
    """
    Unmark a layover flight as interested. This undoes add_layover.
    """
    cur = db.cursor()
    cur.execute(
        """
        DELETE FROM layovers
        WHERE iata_code = ? AND depart = ? AND arrive = ? AND user_id = ?
        """,
        (body.iata, body.depart, body.arrive, user.id),
    )
    db.commit()


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


@app.get("/api/layovers/{iata_code}")
def get_layovers_for_airport(
    iata_code: str, 
    user: AuthorizedUser = Depends(get_authorized_user)
) -> list[UserResponse]:
    return get_users_in_layover(user.id, iata_code)
