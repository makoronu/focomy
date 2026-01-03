# Fly.ioデプロイ

## やること
- 初回 → fly_setup.md
- 再デプロイ → `fly deploy`

## スキーマ変更時（モデル変更があった場合）

```bash
# 1. 本番DBに接続
fly postgres connect -a focomy-cms-db -d focomy_cms

# 2. テーブル構造確認
\d user_auth
\d entities
# ...

# 3. 必要なALTER TABLE実行
ALTER TABLE xxx ADD COLUMN IF NOT EXISTS yyy TYPE;
```

**注意**: models/*.py を変更した場合は必ず確認

## 完了条件
- [ ] `fly deploy` 成功
- [ ] `curl https://focomy-cms.fly.dev/health` → OK
- [ ] スキーマ変更時: 本番DBカラム確認

## 次 → ../4_verify/pip_test.md
