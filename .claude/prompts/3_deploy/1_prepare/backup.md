# 本番DBバックアップ

## やること
本番DBのバックアップを取得

## コマンド
```bash
ssh -i ~/.ssh/REA.pem root@sas.realestateautomation.net "pg_dump -U postgres sas > /tmp/backup_$(date +%Y%m%d_%H%M%S).sql"
```

## 確認
- ファイルサイズが0でないこと
- 直近のバックアップがあること

## 完了条件
- [ ] バックアップ取得した
- [ ] ファイルサイズ確認した

## 次の工程
→ env.md
