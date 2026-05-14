-- migrations/012_add_updated_at_to_saved_searches.sql
-- Add updated_at column to rico_saved_searches table for Neon DB compatibility
-- Run once: psql $DATABASE_URL -f migrations/012_add_updated_at_to_saved_searches.sql

ALTER TABLE rico_saved_searches
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

UPDATE rico_saved_searches
SET updated_at = created_at
WHERE updated_at IS NULL;

-- Auto-update updated_at column
CREATE OR REPLACE FUNCTION update_saved_searches_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_saved_searches_updated_at ON rico_saved_searches;

CREATE TRIGGER trg_saved_searches_updated_at
    BEFORE UPDATE ON rico_saved_searches
    FOR EACH ROW
    EXECUTE FUNCTION update_saved_searches_updated_at();
