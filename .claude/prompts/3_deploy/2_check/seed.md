# シード確認

## やること
reset/seed系コマンドが含まれていないか確認

## 禁止パターン
- prisma migrate reset
- seed実行
- deleteMany

## 確認
```bash
git diff origin/main | grep -E "reset|seed|deleteMany"
```

## 完了条件
- [ ] 危険コマンドなし

## 次の工程
→ ../3_execute/build.md
