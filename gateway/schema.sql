-- Trip Orders gateway: a mailbox between the drivers' phones and the office PCs.
-- Nothing here is a source of truth: the office database is. Items are deleted when the office acknowledges them,
-- and by a daily cleanup after RETENTION_DAYS.
CREATE TABLE IF NOT EXISTS cards (
  token_hash   TEXT PRIMARY KEY,          -- sha256 of the link token; the token itself is never stored
  trip_id      TEXT NOT NULL,
  body         TEXT NOT NULL,             -- the card the driver sees (JSON)
  cancelled    INTEGER NOT NULL DEFAULT 0,
  bound_device TEXT,                      -- first phone that used the link
  expires_at   INTEGER,                   -- unix seconds
  updated_at   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid       TEXT NOT NULL UNIQUE,        -- made on the phone: retrying never duplicates
  token_hash TEXT NOT NULL,
  trip_id    TEXT NOT NULL,
  type       TEXT NOT NULL,
  body       TEXT NOT NULL,
  device_id  TEXT NOT NULL,
  phone_at   TEXT,
  recv_at    INTEGER NOT NULL,
  second     INTEGER NOT NULL DEFAULT 0   -- sent from a phone other than the bound one
);
CREATE TABLE IF NOT EXISTS photos (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid       TEXT NOT NULL UNIQUE,
  token_hash TEXT NOT NULL,
  trip_id    TEXT NOT NULL,
  kind       TEXT NOT NULL,
  fallback   INTEGER NOT NULL DEFAULT 0,  -- picked from the gallery instead of the live camera
  event_uuid TEXT,
  sha256     TEXT NOT NULL,
  size       INTEGER NOT NULL,
  data       BLOB NOT NULL,
  recv_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rate (key TEXT NOT NULL, window INTEGER NOT NULL, count INTEGER NOT NULL, PRIMARY KEY (key, window));
CREATE INDEX IF NOT EXISTS events_recv ON events (recv_at);
CREATE INDEX IF NOT EXISTS photos_recv ON photos (recv_at);
