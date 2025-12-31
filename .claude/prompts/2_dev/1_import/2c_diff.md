# 差分インポート

## 目的
- 2回目以降は差分のみインポート
- 更新・削除の検出

## やること
1. `DiffDetector`作成
2. `wp_id`と`wp_modified`で差分判定
3. 新規/更新/削除の分類
4. 差分インポートUI作成

## 参照
- `docs/wordpress_import_plan.md` Phase 2

## 完了条件
- [ ] 新規/更新/変更なし/削除が表示
- [ ] 差分のみインポート可能

## 次 → `2_dryrun.md`（戻る）
