-- migrations/010_password_reset_tokens.sql
-- Password reset token store.
-- Only SHA-256 hashes are stored — plaintext tokens are never persisted.
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          SERIAL      PRIMARY KEY,
    user_email  TEXT        NOT NULL,
    token_hash  TEXT        NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prt_token_hash ON password_reset_tokens (token_hash);
CREATE INDEX IF NOT EXISTS idx_prt_user_email  ON password_reset_tokens (user_email);
