-- migrations/008_onboarding_state.sql
-- Server-side onboarding state for Rico users.
-- Run once: psql $DATABASE_URL -f migrations/008_onboarding_state.sql

CREATE TABLE IF NOT EXISTS rico_onboarding_states (
    user_id      TEXT        PRIMARY KEY,
    status       TEXT        NOT NULL DEFAULT 'pending'
                                 CHECK (status IN ('pending', 'in_progress', 'completed')),
    completed_at TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
