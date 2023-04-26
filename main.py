from datetime import date
import asyncio
import os
import base64
import bcrypt
import time
import hashlib
from typing import cast, Annotated
from sqlite3 import IntegrityError

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Response,
    Query,
    UploadFile,
)
from mimetypes import MimeTypes
from snowflake import SnowflakeGenerator

import httputil
import limiter
from db import db
from deps import get_authorized_user
from models import *
from flights import (
    fetch_flight_details,
    fetch_flights,
    fetch_flight_details,
)
from layovers import set_popularity_for_flights, get_users_in_layover
from airports import (
    find_by_name as find_airports_by_name,
    find_by_coords as find_airports_by_coords,
    get_by_iata as get_airport_by_iata,
)

load_dotenv()


TOKEN_EXPIRY = 604800  # 1 week
MAX_UPLOAD_SIZE = 1024 * 1024 * 1  # 1 MB


app = FastAPI(
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


mime = MimeTypes()
id_generator = SnowflakeGenerator(0)

login_user_limit = limiter.new(limiter.Rate(30, limiter.Duration.MINUTE))
register_limit = limiter.new(limiter.Rate(10, limiter.Duration.MINUTE))
upload_limit = limiter.new(limiter.Rate(5, limiter.Duration.MINUTE))


def validate_iata(origin, dest):
    if origin is None or dest is None:
        raise HTTPException(status_code=400, detail="Invalid IATA code")

    if len(origin) != 3 or len(dest) != 3:
        raise HTTPException(status_code=400, detail="Invalid IATA code")

    if get_airport_by_iata(origin) is None:
        raise HTTPException(status_code=400, detail="Invalid origin airport")

    if get_airport_by_iata(dest) is None:
        raise HTTPException(status_code=400, detail="Invalid destination airport")


@app.get("/api/ping")
def ping():
    return "Pong!!!"


@app.post("/api/login")
async def login(request: LoginRequest) -> LoginResponse:
    await limiter.wait(lambda: login_user_limit.ratelimit(request.email, delay=True))

    cur = db.cursor()
    res = cur.execute(
        "SELECT id, passhash, first_name, profile_picture FROM users WHERE email = ?",
        (request.email,),
    )

    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bcrypt.checkpw(request.password.encode(), row[1].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

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
async def register(request: RegisterRequest):
    await limiter.wait(lambda: register_limit.ratelimit(delay=True))

    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE email = ?", (request.email,))
    if cur.fetchone() is not None:
        raise HTTPException(status_code=409, detail="Email already in use")

    id = str(next(id_generator))
    passhash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()

    try:
        cur.execute(
            "INSERT INTO users (id, email, first_name, passhash) VALUES (?, ?, ?, ?)",
            (id, request.email, request.first_name, passhash),
        )
        db.commit()
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Failed to create user")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create user")


@app.get("/api/me")
def me(user: Annotated[AuthorizedUser, Depends(get_authorized_user)]) -> UserResponse:
    cur = db.cursor()

    res = cur.execute(
        "SELECT id, email, first_name, profile_picture FROM users WHERE id = ?",
        (user.id,),
    )

    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=500)

    return UserResponse(**row)


@app.patch("/api/me")
def update_me(
    user: Annotated[AuthorizedUser, Depends(get_authorized_user)],
    update: MeUpdate,
) -> UserResponse:
    cur = db.cursor()

    q = "UPDATE users SET "
    v = []

    if update.email is not None:
        q += "email = ?, "
        v.append(update.email)

    if update.first_name is not None:
        q += "first_name = ?, "
        v.append(update.first_name)

    if update.profile_picture is not None:
        q += "profile_picture = ?, "
        v.append(update.profile_picture)

    if len(v) != 0:
        q = q[:-2] + " WHERE id = ?"
        v.append(user.id)

        cur.execute(q, v)
        db.commit()

    return me(user)


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


@app.get("/api/flights")
async def get_flights(
    user: Annotated[AuthorizedUser, Depends(get_authorized_user)],
    origin: Annotated[str, Query(description="3-letter airport code (IATA)")],
    dest: Annotated[str, Query(description="3-letter airport code (IATA)")],
    date: Annotated[
        date, Query(description="date of first flight in YYYY-MM-DD format")
    ],
    return_date: Annotated[
        date, Query(description="date of the returning flight in YYYY-MM-DD format")
    ],
    num_adults: Annotated[int, Query(description="number of adults")] = 1,
    wait_time: Annotated[
        int, Query(description="max wait time in milliseconds", ge=0, le=5000)
    ] = 500,
    page: Annotated[int, Query(description="page number", ge=1)] = 1,
) -> list[FlightDetailResponse]:
    PAGE_SIZE = 5

    validate_iata(origin, dest)

    if date > return_date:
        raise HTTPException(status_code=400, detail="Invalid dates")

    search_cache_key = {
        "origin": origin,
        "dest": dest,
        "date": date,
        "return_date": return_date,
    }

    search: FlightApiResponse
    # TODO: implement eviction for old cached flights
    if (search_data := httputil.get_cached(search_cache_key)) is not None:
        search = FlightApiResponse.parse_raw(search_data)
    else:
        try:
            search = await fetch_flights(
                origin,
                dest,
                date,
                return_date,
                num_adults,
                wait_time,
                user.id,
            )
        except HTTPException as e:
            raise e
        except limiter.LimitedException as e:
            limiter.raise_http(e)
        except Exception as e:
            httputil.raise_external(e)

        if search.status:
            httputil.set_cache(search_cache_key, search.json())

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

        if (cache := httputil.get_cached(cacheKey)) is not None:
            details[i] = FlightDetailResponse.parse_raw(cache)
            return

        try:
            res = await fetch_flight_details(
                itineraryId=search.data[i].id,
                origin=origin,
                dest=dest,
                date=date,
                return_date=return_date,
                num_adults=num_adults,
                user_id=user.id,
            )
        except HTTPException as e:
            raise e
        except limiter.LimitedException as e:
            limiter.raise_http(e)
        except Exception as e:
            httputil.raise_external(e)

        if res.status:
            httputil.set_cache(cacheKey, res.json())

        details[i] = res

    coros = [loop(i) for i in range(len(search.data))]
    await asyncio.gather(*coros)

    details_pop = [detail for detail in details if detail is not None]
    set_popularity_for_flights(details_pop)

    return details_pop


@app.get("/api/layovers")
def layovers(
    user: Annotated[AuthorizedUser, Depends(get_authorized_user)],
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
    user: Annotated[AuthorizedUser, Depends(get_authorized_user)],
    body: AddOrRemoveLayoverRequest,
):
    """
    Mark a layover flight as interested. This contributes towards a popularity
    score for each airport.
    """
    if get_airport_by_iata(body.iata) is None:
        raise HTTPException(status_code=404, detail="Airport not found")

    try:
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO layovers (iata_code, depart, arrive, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (body.iata, body.depart, body.arrive, user.id),
        )
        db.commit()
    except HTTPException as e:
        raise e
    except IntegrityError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
    except Exception as e:
        httputil.raise_external(e)


@app.delete("/api/layovers", status_code=204)
def remove_layover(
    user: Annotated[AuthorizedUser, Depends(get_authorized_user)],
    body: AddOrRemoveLayoverRequest,
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


@app.get("/api/layovers/{iata_code}")
def get_layovers_for_airport(
    user: Annotated[AuthorizedUser, Depends(get_authorized_user)],
    iata_code: str,
) -> list[UserResponse]:
    if get_airport_by_iata(iata_code) is None:
        raise HTTPException(status_code=404, detail="Airport not found")

    return get_users_in_layover(user.id, iata_code)


@app.get("/api/airports")
def airports(
    name: Annotated[
        str | None, Query(description="airport name (must not have lat or long)")
    ],
    lat: Annotated[float | None, Query(description="latitude (must also have long)")],
    long: Annotated[float | None, Query(description="longitude (must also have lat)")],
) -> ListAirportsResponse:
    if name:
        airports = find_airports_by_name(name)
    elif lat and long:
        airports = find_airports_by_coords(lat, long)
    else:
        raise HTTPException(status_code=400, detail="need either ?name or ?lat&long")

    return ListAirportsResponse(airports=airports)


@app.get("/api/assets/{hash}/{filename}")
def get_asset(hash: str, filename: str) -> Response:
    cur = db.cursor()
    res = cur.execute(
        """
        SELECT data FROM assets
        WHERE hash = ? AND name = ?
        """,
        (hash, filename),
    )

    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    types = mime.guess_type(filename)[0]
    contentType = types if types is not None else "application/octet-stream"

    return Response(content=row[0], headers={"Content-Type": contentType})


@app.post("/api/assets")
async def upload_asset(
    user: Annotated[AuthorizedUser, Depends(get_authorized_user)],
    file: UploadFile,
) -> AssetUploadResponse:
    try:
        upload_limit.try_acquire(user.id)
    except limiter.LimitedException as e:
        limiter.raise_http(e)

    if file.size is None:
        raise HTTPException(status_code=400, detail="file size is unknown")

    if file.size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size must be less than {MAX_UPLOAD_SIZE} bytes",
        )

    data = file.file.read()
    name = file.filename
    if name is None:
        raise HTTPException(status_code=400, detail="No filename")

    hasher = hashlib.sha256()
    hasher.update(data)
    hash = base64.urlsafe_b64encode(hasher.digest()).decode()

    cur = db.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO assets (hash, name, user_id, data)
        VALUES (?, ?, ?, ?)
        """,
        (hash, file.filename, user.id, data),
    )
    db.commit()
    return AssetUploadResponse(path=f"/api/assets/{hash}/{file.filename}")
