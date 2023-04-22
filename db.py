import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "./sqlite.db")


db = sqlite3.connect(DB_PATH, check_same_thread=False)

with open("schema.sql") as f:
    db.executescript(f.read())
    db.commit()
