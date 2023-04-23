import os
import time
import json
import sqlite3
import tempfile
from typing import Any, Callable

MAX_AGE = 60 * 60 * 24 * 1  # 1 day

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


def get(key: dict) -> str | None:
    keystr = json.dumps(key)

    res = db.execute(
        "SELECT response FROM cache WHERE key = ? AND expiry > ?", (keystr, time.time())
    )
    row = res.fetchone()
    if row is not None:
        return row[0]


def set(key: dict, response: str, max_age: int = MAX_AGE) -> None:
    keystr = json.dumps(key)

    db.execute(
        "REPLACE INTO cache (key, expiry, response) VALUES (?, ?, ?)",
        (keystr, time.time() + max_age, response),
    )
    db.commit()


def use(key: dict, getter: Callable[[], str], maxAge=MAX_AGE) -> str:
    if (cached := get(key)) is not None:
        return cached

    response = getter()
    set(key, response, maxAge)

    return response
