# .env確認

## やること
本番.envが正しいか確認

## 確認ポイント（バックエンド）
- [ ] DATABASE_URLが本番DB
- [ ] API_URLが本番URL
- [ ] SECRET_KEYが本番用
- [ ] DEBUG=false

## 確認ポイント（フロントエンド）⚠️重要
- [ ] NEXT_PUBLIC_API_URL=https://sas.realestateautomation.net
- [ ] NODE_ENV=production
- localhostは絶対NG

## ⚠️ ローカルでビルドする場合（必須）
**NEXT_PUBLIC_*はビルド時に埋め込まれる。ローカルの設定も確認必須！**

- [ ] ローカルの.env.localを確認
- [ ] NEXT_PUBLIC_API_URL=localhost → ビルド時に上書き必須

```bash
# 本番URLでビルド（必須）
NEXT_PUBLIC_API_URL=https://sas.realestateautomation.net npm run build
```

## コマンド
```bash
# バックエンド（本番）
ssh -i ~/.ssh/REA.pem root@sas.realestateautomation.net "cat /opt/SAS/backend/.env | head -10"

# フロントエンド（本番）
ssh -i ~/.ssh/REA.pem root@sas.realestateautomation.net "cat /opt/SAS/frontend/.env.local"

# フロントエンド（ローカル）← 必ず確認！
cat frontend/.env.local | grep NEXT_PUBLIC
```

## 完了条件
- [ ] バックエンド設定を確認した
- [ ] フロントエンド設定を確認した（NEXT_PUBLIC_API_URLが本番URL）

## 中断条件
- 開発用設定 → 停止して報告
- NEXT_PUBLIC_API_URL=localhost → 即修正

## 次の工程
→ config.md
