# ドライラン機能

## 目的
- 本番インポート前にシミュレーション
- 重複・エラー事前検出

## やること
1. `DryRunService`作成
2. `POST /import/{job_id}/dry-run`エンドポイント追加
3. ドライラン結果UI作成
4. 本番インポート前にドライラン必須化

## 参照
- `docs/wordpress_specification.md` セクション3（データマッピング）
- `docs/wordpress_import_plan.md` Phase 1

## 完了条件
- [ ] ドライラン実行可能
- [ ] 結果に重複・警告・エラー表示

## 次 → `2a_preview.md`
