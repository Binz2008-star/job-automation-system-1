-- migrations/007_users.sql
-- Users table for DB-backed authentication.
-- Run once: psql $DATABASE_URL -f migrations/007_users.sql

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL      PRIMARY KEY,
    email           TEXT        NOT NULL UNIQUE,
    password_hash   TEXT        NOT NULL,
    role            TEXT        NOT NULL DEFAULT 'user'
                                    CHECK (role IN ('admin', 'user')),
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Seed the initial admin from env vars at migration time.
-- If ADMIN_EMAIL / ADMIN_PASSWORD_HASH are set in the shell running psql,
-- this inserts the admin row; otherwise it is a no-op.
INSERT INTO users (email, password_hash, role)
VALUES (
    COALESCE(current_setting('app.admin_email',    true), 'admin@localhost'),
    COALESCE(current_setting('app.admin_password_hash', true), ''),
    'admin'
)
ON CONFLICT (email) DO NOTHING;
