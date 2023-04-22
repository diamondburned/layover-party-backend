import json
import os
import requests
import tempfile
import sqlite3
from pydantic import BaseModel, parse_obj_as
from models import Airport


AIRPORTS_JSON = "https://gist.githubusercontent.com/tdreyno/4278655/raw/7b0762c09b519f40397e4c3e100b097d861f5588/airports.json"

WORKING_DIR = os.path.join(tempfile.gettempdir(), "layover-party")
AIRPORTS_DB = os.path.join(WORKING_DIR, "airports.db")

AIRPORTS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS airports (
        iata TEXT PRIMARY KEY,
        name TEXT,
        city TEXT,
        state TEXT,
        country TEXT,
        lat REAL,
        long REAL
    );
    
    CREATE INDEX IF NOT EXISTS airports_name ON airports (name);
    CREATE INDEX IF NOT EXISTS airports_city ON airports (lat, long);
"""


class __airport(BaseModel):
    code: str
    lat: str
    lon: str
    name: str
    city: str
    state: str | None
    country: str
    woeid: int
    tz: str
    phone: str
    type: str
    email: str
    url: str
    icao: str
    direct_flights: int
    carriers: int


def __download_airports_json() -> list[__airport]:
    res = requests.get(AIRPORTS_JSON)
    res.raise_for_status()
    return parse_obj_as(list[__airport], res.json())


def __init_db() -> sqlite3.Connection:
    os.makedirs(WORKING_DIR, exist_ok=True)

    db = sqlite3.connect(AIRPORTS_DB, check_same_thread=False)

    cur = db.cursor()
    cur.executescript(AIRPORTS_SCHEMA)

    res = cur.execute("SELECT COUNT(*) FROM airports")
    if res.fetchone()[0] == 0:
        print("Downloading airports.json...")
        airports = __download_airports_json()

        print("Inserting airports into database...")
        cur.executemany(
            "INSERT INTO airports VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    airport.code,
                    airport.name,
                    airport.city,
                    airport.state,
                    airport.country,
                    airport.lat,
                    airport.lon,
                )
                for airport in airports
            ],
        )

    db.commit()
    return db


db = __init_db()


def find_by_coords(lat: float, long: float, limit=10) -> list[Airport]:
    cur = db.cursor()
    res = cur.execute(
        "SELECT * FROM airports ORDER BY (lat - ?) * (lat - ?) + (long - ?) * (long - ?) LIMIT ?",
        (lat, lat, long, long, limit),
    )

    rows = res.fetchall()
    return [
        Airport(
            iata=row[0],
            name=row[1],
            city=row[2],
            state=row[3],
            country=row[4],
            lat=row[5],
            long=row[6],
        )
        for row in rows
    ]


def find_by_name(name: str, limit=10) -> list[Airport]:
    cur = db.cursor()
    res = cur.execute(
        "SELECT * FROM airports WHERE name LIKE ? OR iata LIKE ? OR city LIKE ? LIMIT ?",
        (f"%{name}%", f"%{name}%", f"%{name}%", limit),
    )

    rows = res.fetchall()
    return [
        Airport(
            iata=row[0],
            name=row[1],
            city=row[2],
            state=row[3],
            country=row[4],
            lat=row[5],
            long=row[6],
        )
        for row in rows
    ]


def get_by_iata(iata: str) -> Airport:
    cur = db.cursor()
    res = cur.execute("SELECT * FROM airports WHERE iata = ?", (iata,))

    row = res.fetchone()
    return Airport(
        iata=row[0],
        name=row[1],
        city=row[2],
        state=row[3],
        country=row[4],
        lat=row[5],
        long=row[6],
    )
