PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA strict=ON;

CREATE TABLE IF NOT EXISTS users (
	id TEXT PRIMARY KEY,
	email TEXT UNIQUE,
	passhash TEXT NOT NULL,
	first_name TEXT NOT NULL,
	profile_picture TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
	token TEXT PRIMARY KEY,
	user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
	expiration INTEGER NOT NULL
);

DROP TABLE IF EXISTS flight_responses;

CREATE TABLE IF NOT EXISTS layovers (
	user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
	iata_code TEXT NOT NULL,
	arrive INTEGER NOT NULL,
	depart INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS layovers_unique_idx
	ON layovers(user_id, iata_code, arrive, depart);
