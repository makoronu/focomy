-- Migration: Add version column to entities table
-- Date: 2026-01-16
-- Issue: 500 error on forms page due to missing version column
-- Affects: Sites installed before 2025-12-28

-- ==========================================
-- BACKUP FIRST (Required by protocol)
-- ==========================================
-- pg_dump -h <host> -U <user> -d <dbname> > backup_before_version_migration.sql

-- PostgreSQL
ALTER TABLE entities
ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

-- Verify
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'entities' AND column_name = 'version';
