-- Migration: Add missing columns to import_jobs table
-- Date: 2025-12-31
-- Description: Add dry_run_result, checkpoint, and other columns

-- Forward migration
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS dry_run_result JSON;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS checkpoint JSON;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS posts_imported INTEGER DEFAULT 0;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS pages_imported INTEGER DEFAULT 0;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS media_imported INTEGER DEFAULT 0;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS categories_imported INTEGER DEFAULT 0;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS tags_imported INTEGER DEFAULT 0;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS authors_imported INTEGER DEFAULT 0;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS menus_imported INTEGER DEFAULT 0;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS redirects_generated INTEGER DEFAULT 0;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS errors JSON;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS warnings JSON;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS created_by VARCHAR(36);
