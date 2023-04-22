import json
import os
import base64
import bcrypt
import time

from dotenv import load_dotenv, main
from requests import request
from pydantic import BaseModel
from fastapi import FastAPI, Depends, HTTPException, Request

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


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expiry: int
    attributes: dict


class RegisterRequest(BaseModel):
    email: str
    first_name: str
    password: str


class MeResponse(BaseModel):
    email: str
    id: str
    first_name: str


class ListAirportsResponse(BaseModel):
    airports: list[Airport]


@app.post("/api/login")
def login(request: LoginRequest) -> LoginResponse:
    cur = db.cursor()
    res = cur.execute(
        "SELECT passhash, attributes FROM users WHERE email = ?", (request.email,)
    )

    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=401)

    if not bcrypt.checkpw(request.password.encode(), row[0].encode()):
        raise HTTPException(status_code=401)

    token = base64.b64encode(os.urandom(32)).decode()
    expire = int(time.time()) + TOKEN_EXPIRY
    cur.execute(
        "INSERT INTO sessions (email, token, expiration) VALUES (?, ?, ?)",
        (request.email, token, expire),
    )
    db.commit()

    return LoginResponse(token=token, expiry=expire, attributes=json.loads(row[1]))


@app.post("/api/register")
def register(request: RegisterRequest):
    passhash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()

    cur = db.cursor()
    cur.execute(
        "INSERT INTO users (email, first_name, passhash) VALUES (?, ?, ?)",
        (request.email, request.first_name, passhash),
    )
    db.commit()


class AuthorizedUser:
    email: str

    def __init__(self, email: str):
        self.email = email


def get_authorized_user(request: Request) -> AuthorizedUser:
    unauthorized_paths = ["/api/login", "/api/register"]
    if request.url.path in unauthorized_paths:
        raise ValueError("path doesn't have authorization")

    token = request.headers.get("Authorization")
    if token is None:
        raise HTTPException(status_code=401)

    cur = db.cursor()
    res = cur.execute(
        "SELECT email FROM sessions WHERE token = ? AND expiration > ?",
        (token, int(time.time())),
    )
    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=401)

    return AuthorizedUser(row[0])


@app.get("/api/me")
def me(user: AuthorizedUser = Depends(get_authorized_user)) -> MeResponse:
    cur = db.cursor()
    res = cur.execute("SELECT attributes FROM users WHERE email = ?", (user.email,))
    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=500)

    data = json.loads(row[0])
    return MeResponse(**data)


class FlightsRequest(BaseModel):
    date: str
    origin: str
    destination: str
    num_adults: int


@app.get("/api/flights")
def get_flights(
    date: str, origin: str, dest: str, num_adults: int, waitTime: int | None = None
) -> FlightResponse:
    """
    date: date of flight in YYYYMMDD format
    origin: 3-letter airport code
    dest: 3-letter airport code
    num_adults: number of adults
    waitTime: time in milliseconds to wait for a response
    """

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
        "waitTime": min(waitTime, 1500) if waitTime is not None else 500,
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
    user: AuthorizedUser = Depends(get_authorized_user),
) -> ListAirportsResponse:
    if name:
        airports = find_airports_by_name(name)
    elif lat and long:
        airports = find_airports_by_coords(lat, long)
    else:
        raise HTTPException(status_code=400, detail="need either ?name or ?lat&long")

    return ListAirportsResponse(airports=airports)
