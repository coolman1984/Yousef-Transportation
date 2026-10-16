-- Authoritative insert-only ledger of trial windows per device (d) or machine (m).
-- Back up D1 before applying. Safe to re-run (CREATE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS schema_migrations (
  id         TEXT PRIMARY KEY,
  applied_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trial_grants (
  product        TEXT NOT NULL,
  subject_kind   TEXT NOT NULL CHECK (subject_kind IN ('m', 'd')),
  subject        TEXT NOT NULL,
  first_day      TEXT NOT NULL,
  last_day       TEXT NOT NULL,
  created_at     TEXT NOT NULL,
  source_request TEXT,
  PRIMARY KEY (product, subject_kind, subject)
);

CREATE TRIGGER IF NOT EXISTS trial_grants_no_update
BEFORE UPDATE ON trial_grants
BEGIN
  SELECT RAISE(ABORT, 'trial_grants is insert-only');
END;

CREATE TRIGGER IF NOT EXISTS trial_grants_no_delete
BEFORE DELETE ON trial_grants
BEGIN
  SELECT RAISE(ABORT, 'trial_grants is insert-only');
END;
