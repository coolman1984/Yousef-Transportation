-- Resumable legacy trial_grants backfill (PR B r2). Safe to re-run.

CREATE TABLE IF NOT EXISTS schema_migrations (
  id         TEXT PRIMARY KEY,
  applied_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trial_grants_backfill_staging (
  product        TEXT NOT NULL,
  subject_kind   TEXT NOT NULL CHECK (subject_kind IN ('m', 'd')),
  subject        TEXT NOT NULL,
  first_day      TEXT NOT NULL,
  last_day       TEXT NOT NULL,
  source_request TEXT,
  PRIMARY KEY (product, subject_kind, subject)
);

CREATE TABLE IF NOT EXISTS trial_grants_backfill_progress (
  id          INTEGER PRIMARY KEY CHECK (id = 1),
  phase       TEXT NOT NULL,
  after_rowid INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trial_issue_batch_sentinel (
  singleton INTEGER PRIMARY KEY CHECK (singleton = -1)
);
