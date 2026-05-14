-- migrations/005_mvp_settings_pipeline_runs.sql
-- Phase 1 MVP: settings table + pipeline run tracking
-- Run once: psql $DATABASE_URL -f migrations/005_mvp_settings_pipeline_runs.sql

-- -----------------------------------------------------------------
-- Settings table (multi-user ready)
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    user_id           TEXT        PRIMARY KEY,
    min_score         INTEGER     NOT NULL CHECK (min_score BETWEEN 0 AND 100) DEFAULT 50,
    max_daily_applies INTEGER     NOT NULL CHECK (max_daily_applies >= 0) DEFAULT 10,
    notifications     JSONB       NOT NULL DEFAULT '{}',   -- e.g., {"telegram": {"chat_id": "123"}, "email": true}
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert default row for single-user MVP (user_id = 'default')
INSERT INTO settings (user_id) VALUES ('default')
ON CONFLICT (user_id) DO NOTHING;

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_settings_updated_at
    BEFORE UPDATE ON settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- -----------------------------------------------------------------
-- Normalized keyword tables (optional but recommended)
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_include_keywords (
    user_id    TEXT      NOT NULL,
    keyword    TEXT      NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, keyword)
);

CREATE TABLE IF NOT EXISTS user_exclude_keywords (
    user_id    TEXT      NOT NULL,
    keyword    TEXT      NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, keyword)
);

-- For quick lookups
CREATE INDEX IF NOT EXISTS idx_include_keywords_user ON user_include_keywords (user_id);
CREATE INDEX IF NOT EXISTS idx_exclude_keywords_user ON user_exclude_keywords (user_id);

-- -----------------------------------------------------------------
-- Pipeline runs (audit log)
-- -----------------------------------------------------------------
CREATE TYPE pipeline_status AS ENUM ('running', 'done', 'failed');

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           SERIAL        PRIMARY KEY,
    started_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    finished_at  TIMESTAMPTZ,
    status       pipeline_status NOT NULL DEFAULT 'running',
    jobs_found   INTEGER       NOT NULL DEFAULT 0,
    jobs_scored  INTEGER       NOT NULL DEFAULT 0,
    jobs_applied INTEGER       NOT NULL DEFAULT 0,
    error        TEXT,
    UNIQUE (started_at, id)   -- for idempotency
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at ON pipeline_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs (status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_finished_at ON pipeline_runs (finished_at);

-- Optional: view for latest run
CREATE VIEW latest_pipeline_run AS
SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1;

COMMENT ON TABLE settings IS 'User preferences for job matching and daily limits';
COMMENT ON COLUMN settings.notifications IS 'JSON structure for per-channel notification settings';
COMMENT ON TABLE pipeline_runs IS 'Log of each daily pipeline execution for monitoring';
