# チェックポイント機能

## 目的
- インポート途中で失敗しても再開可能
- 処理済みIDを記録

## やること
1. `CheckpointManager`作成
2. 各フェーズ完了時にチェックポイント保存
3. 再開時にスキップ済みIDを除外
4. `POST /import/{job_id}/resume`エンドポイント追加

## 参照
- `docs/wordpress_import_plan.md` セクション3.1

## 完了条件
- [ ] 途中停止後に再開可能
- [ ] 重複インポートなし

## 次 → `2c_diff.md`
