# ロールバック機能

## 目的
- インポート後に元の状態に戻せる
- 30日間有効

## やること
1. インポート時に`wp_id`記録（既存）
2. `RollbackService`作成
3. `POST /import/{job_id}/rollback`エンドポイント追加
4. ロールバック確認UI作成

## 参照
- `docs/wordpress_import_plan.md` セクション6.2

## 完了条件
- [ ] ロールバックで全インポートデータ削除
- [ ] リダイレクトも削除

## 次 → `4_sanitize.md`
