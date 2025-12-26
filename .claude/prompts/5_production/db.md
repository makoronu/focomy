# DB操作

## やること
1. 必要ならバックアップ: `pg_dump -U sas_user sas > /tmp/backup.sql`
2. マイグレーション: `cd /opt/SAS/backend && alembic upgrade head`
3. 確認: `psql -U sas_user -d sas -c "SELECT 1"`

## 禁止
- バックアップなしでデータ変更

## 次の工程
→ verify.md
