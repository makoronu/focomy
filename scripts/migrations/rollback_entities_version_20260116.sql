-- Rollback: Remove version column from entities table
-- Date: 2026-01-16
-- WARNING: This will break Focomy versions >= 0.1.x that require version column

-- PostgreSQL
ALTER TABLE entities
DROP COLUMN IF EXISTS version;

-- Verify
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'entities' AND column_name = 'version';
-- Should return empty result
