# 修正適用

## やること
1. マイグレーションを本番で実行
2. 実行結果を確認

## コマンド
```bash
ssh rea-conoha "sudo -u postgres psql real_estate_db < /path/to/migration.sql"
```

## 完了条件
- [ ] マイグレーション実行完了
- [ ] エラーなし

## 次 → ../3_verify/verify.md
