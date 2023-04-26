import time
from typing import Annotated

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from models import AuthorizedUser
from db import db


def get_authorized_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())]
) -> AuthorizedUser:
    cur = db.cursor()
    res = cur.execute(
        "SELECT user_id FROM sessions WHERE token = ? AND expiration > ?",
        (credentials.credentials, int(time.time())),
    )
    row = res.fetchone()
    if row is None:
        raise HTTPException(status_code=401)

    return AuthorizedUser(row[0])
