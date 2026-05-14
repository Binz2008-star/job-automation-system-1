-- migrations/009_saved_searches.sql
-- Saved job searches for Rico users.
-- Run once: psql $DATABASE_URL -f migrations/009_saved_searches.sql

CREATE TABLE IF NOT EXISTS rico_saved_searches (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES rico_users(id) ON DELETE CASCADE,
    query       TEXT        NOT NULL,
    filters     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rico_saved_searches_user_id_idx
    ON rico_saved_searches (user_id, created_at DESC);
