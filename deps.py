import time

from fastapi import Request, HTTPException

from models import AuthorizedUser
from db import db


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
