# Fly.io 初回セットアップ

## やること
1. `fly apps create focomy`
2. `fly postgres create --name focomy-db --region nrt`
3. `fly postgres attach focomy-db`
4. `fly secrets set FOCOMY_DATABASE_URL="..."`
5. `fly secrets set FOCOMY_SECRET_KEY="$(openssl rand -hex 32)"`
6. `fly deploy`

## 完了条件
- [ ] ヘルスチェックOK

## 次 → fly.md（確認へ戻る）
