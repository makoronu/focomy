# 型チェック

## やること
1. TypeScriptエラー確認
2. Pythonエラー確認

## コマンド
```bash
# フロント
cd sas-frontend && npx tsc --noEmit

# バックエンド
cd sas-backend && python -m py_compile app/**/*.py
```

## 完了条件
- [ ] TypeScriptエラーなし
- [ ] Pythonエラーなし

## 中断条件
- エラーあり → 修正してから次へ

## 次の工程
→ quality.md
