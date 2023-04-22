from pydantic import BaseModel
from db import db
from typing import TypedDict
import fastapi
import json
import os
import sqlite3
import base64
import bcrypt
import time

TOKEN_EXPIRY = 604800  # 1 week


app = fastapi.FastAPI()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expiry: int
    attributes: dict


class RegisterRequest(BaseModel):
    email: str
    password: str


class MeResponse(BaseModel):
    email: str
    attributes: dict


@app.post("/api/login")
def login(request: LoginRequest) -> LoginResponse:
    cur = db.cursor()
    res = cur.execute(
        "SELECT passhash, attributes FROM users WHERE email = ?", (request.email,)
    )

    row = res.fetchone()
    if row is None:
        raise fastapi.HTTPException(status_code=401)

    if not bcrypt.checkpw(request.password.encode(), row[0].encode()):
        raise fastapi.HTTPException(status_code=401)

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
        "INSERT INTO users (email, passhash, attributes) VALUES (?, ?, ?)",
        (request.email, passhash, json.dumps({})),
    )
    db.commit()


@app.middleware("http")
async def must_authorize(request: fastapi.Request, call_next):
    unauthorized_paths = ["/api/login", "/api/register"]
    if request.url.path in unauthorized_paths:
        return await call_next(request)

    token = request.headers.get("Authorization")
    if token is None:
        raise fastapi.HTTPException(status_code=401)

    cur = db.cursor()
    res = cur.execute(
        "SELECT email FROM sessions WHERE token = ? AND expiration > ?",
        (token, int(time.time())),
    )
    row = res.fetchone()
    if row is None:
        raise fastapi.HTTPException(status_code=401)

    request.state.email = row[0]
    return await call_next(request)


def get_current_email(request: fastapi.Request) -> str:
    if not hasattr(request.state, "email"):
        raise fastapi.HTTPException(status_code=401)
    return request.state.email


@app.get("/api/me")
def me(request: fastapi.Request) -> MeResponse:
    email = get_current_email(request)

    cur = db.cursor()
    res = cur.execute("SELECT attributes FROM users WHERE email = ?", (email,))
    row = res.fetchone()
    if row is None:
        raise fastapi.HTTPException(status_code=500)

    return MeResponse(email=email, attributes=json.loads(row[0]))
