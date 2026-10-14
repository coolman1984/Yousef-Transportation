-- Additive: record owner grant tier and paid expiry on requests and customers.
ALTER TABLE licence_requests ADD COLUMN licence_tier TEXT NOT NULL DEFAULT '';
ALTER TABLE licence_requests ADD COLUMN licence_expiry TEXT;
ALTER TABLE customers ADD COLUMN licence_tier TEXT NOT NULL DEFAULT '';
ALTER TABLE customers ADD COLUMN licence_expiry TEXT;
