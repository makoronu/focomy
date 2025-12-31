# プレビュー機能

## 目的
- 数件だけ実際にインポートして確認
- 問題あればロールバック

## やること
1. `PreviewService`作成
2. `POST /import/{job_id}/preview`エンドポイント追加
3. プレビュー用トランザクション（コミット前に確認）
4. 確定 or 破棄のUI作成

## 参照
- `docs/wordpress_import_plan.md` セクション1.2

## 完了条件
- [ ] 3件程度のプレビューインポート可能
- [ ] 確定/破棄が選択可能

## 次 → `2b_checkpoint.md`
