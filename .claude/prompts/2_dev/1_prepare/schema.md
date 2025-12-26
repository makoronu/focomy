# スキーマ確認

## やること
1. 変更対象テーブルを特定
2. column_labelsからスキーマ取得
3. 型・必須・バリデーション確認

## 確認コマンド
```sql
SELECT column_name, data_type, label_ja, options
FROM column_labels
WHERE table_name = '[対象テーブル]';
```

## 完了条件
- [ ] 対象カラムの型を確認した
- [ ] バリデーションルールを確認した

## 中断条件
- スキーマにないカラム → 停止して確認

## 次の工程
→ existing.md
