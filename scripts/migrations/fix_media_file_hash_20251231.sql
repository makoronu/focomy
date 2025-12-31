-- Migration: Add file_hash column to media table
-- Date: 2025-12-31
-- Description: Add file_hash column for duplicate detection

-- Forward migration
ALTER TABLE media ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64);
CREATE INDEX IF NOT EXISTS ix_media_file_hash ON media(file_hash);

-- Rollback (run manually if needed):
-- DROP INDEX IF EXISTS ix_media_file_hash;
-- ALTER TABLE media DROP COLUMN IF EXISTS file_hash;
