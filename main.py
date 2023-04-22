import json
import os
import base64
import bcrypt
import time

from dotenv import load_dotenv, main
from requests import request
from pydantic import BaseModel
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from snowflake import SnowflakeGenerator

from airports import (
    find_by_name as find_airports_by_name,
    find_by_coords as find_airports_by_coords,
    Airport,
)

from db import db
from models import FlightResponse

load_dotenv()

TOKEN_EXPIRY = 604800  # 1 week


app = FastAPI()
id_generator = SnowflakeGenerator(0)


@app.get("/api/ping")
def ping():
    return "Pong!!!"


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    id: str
    token: str
    expiry: int


class RegisterRequest(BaseModel):
    email: str
    password: str
    first_name: str


class MeResponse(BaseModel):
    id: str
    email: str
    first_name: str
    profile_picture: str | None


class ListAirportsResponse(BaseModel):
    airports: list[Airport]


@app.post("/api/login")
def login(request: LoginRequest) -> LoginResponse:
    cur = db.cursor()
    res = cur.execute(
        "SELECT id, passhash FROM users WHERE email = ?", (request.email,)
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


class AuthorizedUser:
    id: str

    def __init__(self, id: str):
        self.id = id


def get_authorized_user(request: Request) -> AuthorizedUser:
    unauthorized_paths = ["/api/login", "/api/register"]
    if request.url.path in unauthorized_paths:
        raise ValueError("path doesn't have authorization")

    token = request.headers.get("Authorization")
    if token is None:
        raise HTTPException(status_code=401)

    cur = db.cursor()
    res = cur.execute(
        "SELECT user_id FROM sessions WHERE token = ? AND expiration > ?",
        (token, int(time.time())),
    )
    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=401)

    return AuthorizedUser(row[0])


@app.get("/api/me")
def me(user: AuthorizedUser = Depends(get_authorized_user)) -> MeResponse:
    cur = db.cursor()
    res = cur.execute(
        "SELECT id, email, first_name, profile_picture FROM users WHERE id = ?",
        (user.id,),
    )
    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=500)

    return MeResponse(**row)


class FlightsRequest(BaseModel):
    date: str
    origin: str
    destination: str
    num_adults: int


@app.get("/api/flights")
def get_flights(
    date: str = Query(description="date of flight in YYYYMMDD format"),
    origin: str = Query(description="3-letter airport code (IATA)"),
    dest: str = Query(description="3-letter airport code (IATA)"),
    num_adults: int = Query(description="number of adults"),
    wait_time: int | None = Query(None, description="max wait time in minutes"),
) -> FlightResponse:
    host = "skyscanner50.p.rapidapi.com"
    url = "https:// " + host + "/api/v1/searchFlightsMultiStops"

    query_string = {
        "legs": [
            {
                "origin": origin,
                "destination": dest,
                "date": date,
            }
        ],
        "waitTime": min(wait_time, 1500) if wait_time is not None else 500,
        "adults": num_adults,
        "currency": "USD",
        "countryCode": "US",
        "market": "en-US",
    }

    headers = {
        "X-RapidAPI-Key": os.getenv("RAPID_API_KEY"),
        "X-RapidAPI-Host": host,
    }

    res = request("GET", url, headers=headers, params=json.dumps(query_string))

    parsed_res = FlightResponse(**res.json())

    return parsed_res


@app.get("/api/airports")
def airports(
    name: str | None = None,
    lat: float | None = None,
    long: float | None = None,
) -> ListAirportsResponse:
    if name:
        airports = find_airports_by_name(name)
    elif lat and long:
        airports = find_airports_by_coords(lat, long)
    else:
        raise HTTPException(status_code=400, detail="need either ?name or ?lat&long")

    return ListAirportsResponse(airports=airports)
