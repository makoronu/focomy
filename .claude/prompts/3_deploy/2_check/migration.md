# マイグレーション確認

## やること
破壊的なマイグレーションがないか確認

## 禁止事項
- DROP TABLE
- DROP COLUMN
- TRUNCATE
- データ削除

## 確認コマンド
```bash
git diff origin/main -- "**/migrations/*"
```

## 完了条件
- [ ] 破壊的変更なし

## 中断条件
- 破壊的変更あり → 停止して報告

## 次の工程
→ seed.md
