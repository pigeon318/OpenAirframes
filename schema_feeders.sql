CREATE TABLE feeders (
    id          SERIAL PRIMARY KEY,
    key         TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ,
    aircraft_count INTEGER NOT NULL DEFAULT 0,
    message_count  BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_feeders_key ON feeders (key);
