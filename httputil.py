import os
import time
import json
import sqlite3
import tempfile
import traceback
from typing import Any, Callable

from aiohttp import ClientSession
from fastapi import HTTPException


MAX_AGE = 60 * 60 * 24 * 14  # 14 days or 2 weeks

WORKING_DIR = os.path.join(tempfile.gettempdir(), "layover-party")
HTTPCACHE_DB = os.path.join(WORKING_DIR, "httpcache.db")


db = sqlite3.connect(HTTPCACHE_DB, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript(
    """
    PRAGMA journal_mode=WAL;
    PRAGMA strict=ON;

    CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        expiry INTEGER NOT NULL,
    	response TEXT NOT NULL
    );
    """
)
db.commit()

client = ClientSession()


def get_cached(key: dict) -> str | None:
    keystr = json.dumps(key)

    res = db.execute(
        "SELECT response FROM cache WHERE key = ? AND expiry > ?", (keystr, time.time())
    )
    row = res.fetchone()
    if row is not None:
        return row[0]


def __clean_cache(cur=db.cursor()) -> None:
    cur.execute("DELETE FROM cache WHERE expiry < ?", (time.time(),))


def clean_cache() -> None:
    __clean_cache(db.cursor())
    db.commit()


def set_cache(key: dict, response: str, max_age: int = MAX_AGE) -> None:
    keystr = json.dumps(key)

    cur = db.cursor()
    cur.execute(
        "REPLACE INTO cache (key, expiry, response) VALUES (?, ?, ?)",
        (keystr, time.time() + max_age, response),
    )
    __clean_cache(cur)
    db.commit()


def raise_external(e: Exception):
    trace = traceback.format_exc()
    print(f"-------- begin external API error --------")
    print(f"error: {e}")
    print(f"trace:\n{trace}")
    print(f"--------- end external API error ---------")

    raise HTTPException(
        status_code=500,
        detail=f"external API error: {e} (check server console)",
    )
