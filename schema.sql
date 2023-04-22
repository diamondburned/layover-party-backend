PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA strict=ON;

CREATE TABLE IF NOT EXISTS users (
	email TEXT PRIMARY KEY,
	passhash TEXT NOT NULL,
  first_name TEXT NOT NULL,
	profile_picture TEXT,
);

CREATE TABLE IF NOT EXISTS sessions (
	token TEXT PRIMARY KEY,
	email TEXT REFERENCES users(email) ON DELETE CASCADE,
	expiration INTEGER NOT NULL
);
