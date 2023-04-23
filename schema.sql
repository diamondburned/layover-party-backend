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

CREATE TABLE IF NOT EXISTS flight_responses (
	date TEXT NOT NULL,
	origin TEXT NOT NULL,
	destination TEXT NOT NULL,
	timestamp INTEGER NOT NULL,
	response TEXT NOT NULL,

	UNIQUE (date, origin, destination)
);

CREATE TABLE IF NOT EXISTS layovers (
	user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  iata_code TEXT NOT NULL,
  arrive INTEGER NOT NULL,
  depart INTEGER NOT NULL
);
