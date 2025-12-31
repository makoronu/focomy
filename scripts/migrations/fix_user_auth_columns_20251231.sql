-- Migration: Add missing columns to user_auth table
-- Date: 2025-12-31
-- Description: Add reset_token, reset_token_expires, totp_backup_codes, totp_enabled columns

-- Forward migration
ALTER TABLE user_auth ADD COLUMN IF NOT EXISTS reset_token VARCHAR;
ALTER TABLE user_auth ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP;
ALTER TABLE user_auth ADD COLUMN IF NOT EXISTS totp_backup_codes VARCHAR;
ALTER TABLE user_auth ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN DEFAULT FALSE;

-- Rollback (run manually if needed):
-- ALTER TABLE user_auth DROP COLUMN IF EXISTS reset_token;
-- ALTER TABLE user_auth DROP COLUMN IF EXISTS reset_token_expires;
-- ALTER TABLE user_auth DROP COLUMN IF EXISTS totp_backup_codes;
-- ALTER TABLE user_auth DROP COLUMN IF EXISTS totp_enabled;
