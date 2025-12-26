# 影響範囲特定

## やること
1. 関連テーブル特定
2. 関連コード特定
3. 原因箇所を絞り込む

## 確認コマンド
```bash
# DB状態確認
ssh rea-conoha "sudo -u postgres psql real_estate_db -c \"[確認クエリ]\""

# ログ確認
ssh rea-conoha "journalctl -u rea-api --since '1 hour ago'"
```

## 完了条件
- [ ] 原因箇所を特定した

## 次 → ../2_fix/backup.md
