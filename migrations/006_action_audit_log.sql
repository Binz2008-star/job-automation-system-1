-- migrations/006_action_audit_log.sql
-- Agent action audit log + idempotency table
-- Run once:  psql $DATABASE_URL -f migrations/006_action_audit_log.sql

CREATE TABLE IF NOT EXISTS action_audit_log (
    id             SERIAL      PRIMARY KEY,
    action_id      TEXT        NOT NULL,
    action_type    TEXT        NOT NULL,
    user_email     TEXT        NOT NULL DEFAULT '',
    job_id         TEXT,
    job_title      TEXT,
    job_company    TEXT,
    timestamp      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    result_status  TEXT        NOT NULL,   -- success | failure | duplicate
    result_message TEXT,
    duration_ms    INTEGER     NOT NULL DEFAULT 0,
    failure_reason TEXT,
    event_type     TEXT,       -- For general audit events (e.g., profile_question)
    data           JSONB       -- Additional event metadata
);

-- Idempotency check: find duplicate action_ids quickly
CREATE INDEX IF NOT EXISTS idx_audit_action_id
    ON action_audit_log (action_id);

-- Per-user action history
CREATE INDEX IF NOT EXISTS idx_audit_user_email
    ON action_audit_log (user_email, timestamp DESC);

-- General time-series queries
CREATE INDEX IF NOT EXISTS idx_audit_timestamp
    ON action_audit_log (timestamp DESC);

-- Auto-update updated_at column
CREATE OR REPLACE FUNCTION update_audit_log_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_log_updated_at
    BEFORE UPDATE ON action_audit_log
    FOR EACH ROW
    EXECUTE FUNCTION update_audit_log_updated_at();
