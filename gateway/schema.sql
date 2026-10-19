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
  updated_at   INTEGER NOT NULL,
  tenant       TEXT NOT NULL DEFAULT 'legacy'  -- mailbox space; 'legacy' is the old single OFFICE_SECRET
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
  second     INTEGER NOT NULL DEFAULT 0,  -- sent from a phone other than the bound one
  tenant     TEXT NOT NULL DEFAULT 'legacy'
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
  recv_at    INTEGER NOT NULL,
  tenant     TEXT NOT NULL DEFAULT 'legacy'
);
CREATE TABLE IF NOT EXISTS revoked (        -- links the office replaced: a removed card cannot be published again by a PC with old data
  token_hash TEXT PRIMARY KEY,
  at         INTEGER NOT NULL,
  until      INTEGER NOT NULL DEFAULT 0,      -- remembered until the link would have expired (+7 days); 90 days if its card is unknown
  tenant     TEXT NOT NULL DEFAULT 'legacy'
);
CREATE TABLE IF NOT EXISTS tenants (         -- one row per auto-registered office; the secret is NOT stored (it is derived from MASTER_KEY)
  id         TEXT PRIMARY KEY,               -- 128-bit hex
  created_at INTEGER NOT NULL,
  last_seen  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (           -- photo bytes accepted per mailbox per day (abuse limit)
  tenant TEXT NOT NULL,
  day    INTEGER NOT NULL,
  bytes  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant, day)
);
CREATE TABLE IF NOT EXISTS receipts (       -- what the office acknowledged: the phone keeps its copy until it sees the receipt
  uuid TEXT PRIMARY KEY,
  at   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rate (key TEXT NOT NULL, window INTEGER NOT NULL, count INTEGER NOT NULL, PRIMARY KEY (key, window));
CREATE INDEX IF NOT EXISTS events_recv ON events (recv_at);
CREATE INDEX IF NOT EXISTS photos_recv ON photos (recv_at);
CREATE INDEX IF NOT EXISTS events_tenant ON events (tenant, id);
CREATE INDEX IF NOT EXISTS photos_tenant ON photos (tenant, id);
CREATE INDEX IF NOT EXISTS cards_tenant ON cards (tenant);
