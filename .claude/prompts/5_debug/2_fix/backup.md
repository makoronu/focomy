# バックアップ取得

## やること
1. 対象テーブルのバックアップ取得
2. バックアップファイル確認

## コマンド
```bash
ssh rea-conoha "sudo -u postgres pg_dump -t [テーブル名] real_estate_db > /tmp/backup_[テーブル名]_$(date +%Y%m%d_%H%M%S).sql"
```

## 完了条件
- [ ] バックアップファイルが存在する

## 次 → migration.md
