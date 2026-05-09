-- migrations/005_mvp_settings_pipeline_runs.sql
-- Phase 1 MVP: settings table + pipeline run tracking
-- Run once:  psql $DATABASE_URL -f migrations/005_mvp_settings_pipeline_runs.sql

-- User-configurable settings (single-user MVP: user_id = 'default')
CREATE TABLE IF NOT EXISTS settings (
    user_id           TEXT        PRIMARY KEY DEFAULT 'default',
    include_keywords  TEXT[]      NOT NULL DEFAULT '{}',
    exclude_keywords  TEXT[]      NOT NULL DEFAULT '{}',
    min_score         INTEGER     NOT NULL DEFAULT 50,
    max_daily_applies INTEGER     NOT NULL DEFAULT 10,
    telegram_chat_id  TEXT        NOT NULL DEFAULT '',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert the default row so GET /api/v1/settings always returns something
INSERT INTO settings (user_id) VALUES ('default')
ON CONFLICT (user_id) DO NOTHING;

-- Pipeline execution log
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           SERIAL      PRIMARY KEY,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at  TIMESTAMPTZ,
    status       TEXT        NOT NULL DEFAULT 'running',  -- running | done | failed
    jobs_found   INTEGER     NOT NULL DEFAULT 0,
    jobs_scored  INTEGER     NOT NULL DEFAULT 0,
    jobs_applied INTEGER     NOT NULL DEFAULT 0,
    error        TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at
    ON pipeline_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
    ON pipeline_runs (status);
