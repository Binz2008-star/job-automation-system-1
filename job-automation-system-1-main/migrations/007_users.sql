-- migrations/007_users.sql
-- Users table for DB-backed authentication.
-- Run once: psql $DATABASE_URL -f migrations/007_users.sql

-- Enable citext extension for case-insensitive email uniqueness (optional, requires superuser)
-- CREATE EXTENSION IF NOT EXISTS citext;

-- User roles (enum for clarity and future extension)
CREATE TYPE user_role AS ENUM ('admin', 'user', 'service_account');

CREATE TABLE IF NOT EXISTS users (
    id                BIGSERIAL    PRIMARY KEY,
    email             TEXT         NOT NULL UNIQUE,   -- Use citext if extension available
    password_hash     TEXT         NOT NULL,           -- Must be a bcrypt/argon2 hash
    hash_algorithm    TEXT         NOT NULL DEFAULT 'bcrypt',
    role              user_role    NOT NULL DEFAULT 'user',
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    email_verified_at TIMESTAMPTZ,
    last_login_at     TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at        TIMESTAMPTZ   -- soft delete
);

-- Case-insensitive email index (if not using citext)
CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users (lower(email));

-- Index for analytics queries
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at);
CREATE INDEX IF NOT EXISTS idx_users_last_login_at ON users (last_login_at);

-- Automatically update updated_at on row change
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- -------------------------------------------------------------------
-- Admin seeding (safe version)
-- -------------------------------------------------------------------
-- Instead of relying on session variables, create a separate script
-- or use environment variables with psql's \set.
-- Example safe seeding (run after migration if needed):
-- \set admin_email 'admin@example.com'
-- \set admin_password_hash '$2b$12$...'   (bcrypt hash of a strong password)
-- INSERT INTO users (email, password_hash, role) VALUES (:'admin_email', :'admin_password_hash', 'admin')
-- ON CONFLICT (email) DO NOTHING;
-- -------------------------------------------------------------------

COMMENT ON TABLE users IS 'Core user accounts for authentication and authorization';
COMMENT ON COLUMN users.password_hash IS 'One-way hash (bcrypt, argon2) – never store plain text';
COMMENT ON COLUMN users.hash_algorithm IS 'Algorithm used to generate password_hash (for future updates)';
