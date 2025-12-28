# Fly.ioデプロイ

## 事前確認
- [ ] fly auth login 済み
- [ ] fly.toml 設定確認
- [ ] Postgres DB 存在確認 (`fly postgres list`)

---

## 初回デプロイ

### 1. アプリ作成（未作成の場合）
```bash
fly apps create focomy
```

### 2. Postgres作成
```bash
fly postgres create --name focomy-db --region nrt
fly postgres attach focomy-db --app focomy
```

### 3. 環境変数設定
**重要: Focomyは `FOCOMY_` prefix を使用**
```bash
# DB接続（attachで自動設定されるDATABASE_URLをコピー）
fly secrets set FOCOMY_DATABASE_URL="postgres://..." --app focomy

# その他必要な設定
fly secrets set FOCOMY_SECRET_KEY="$(openssl rand -hex 32)" --app focomy
```

### 4. デプロイ
```bash
fly deploy
```

---

## 再デプロイ
```bash
fly deploy
```

---

## 確認
```bash
curl https://focomy.fly.dev/health
```

## 完了条件
- [ ] デプロイ成功
- [ ] ヘルスチェックOK (`{"status":"healthy"}`)

## トラブルシューティング
- DB接続エラー → `fly postgres list` でDB状態確認、停止中なら `fly machine restart -a focomy-db`
- 環境変数エラー → `fly secrets list` で確認、`FOCOMY_` prefix を忘れていないか

## 次 → ../4_verify/pip_test.md
