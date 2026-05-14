-- Migration: Add uniqueness constraint to rico_job_recommendations
-- Purpose: Ensure each user-job combination is unique to prevent duplicates
-- Related: Issue #127 - User isolation and deduplication

-- Step 1: Dedupe existing rows - keep the most recent (highest id) for each user/job_key pair
DELETE FROM rico_job_recommendations a
USING rico_job_recommendations b
WHERE a.user_id = b.user_id
  AND a.job_key = b.job_key
  AND a.id < b.id
  AND a.job_key IS NOT NULL;

-- Step 2: Add unique constraint on (user_id, job_key) to prevent duplicate recommendations
ALTER TABLE rico_job_recommendations
ADD CONSTRAINT rico_recommendations_user_job_unique UNIQUE (user_id, job_key);

-- Step 3: Create index for faster lookups by user_id and job_key
CREATE INDEX IF NOT EXISTS idx_rico_recommendations_user_job_key
ON rico_job_recommendations (user_id, job_key);

-- Step 4: Create index for status filtering with user_id
CREATE INDEX IF NOT EXISTS idx_rico_recommendations_user_status_updated
ON rico_job_recommendations (user_id, status, updated_at DESC);
