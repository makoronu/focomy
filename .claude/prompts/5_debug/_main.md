# デバッグ（大プロンプト）

**本番バグ発生時に使用。プロトコル準拠で修正。**

---

## 緊急時ほどプロンプトを読め

急いでいても、このプロンプトを最後まで読んでから作業開始。
「動いた」で終わらず、全パターンをテストしろ。

---

## PyPIパッケージ問題チェックリスト

PyPI関連のバグの場合、以下を確認:

- [ ] **パス解決**: `Path.cwd()` vs `Path(__file__)` の使い分け
  - ユーザーデータ → `Path.cwd()`（カレントディレクトリ）
  - パッケージ内リソース → `Path(__file__)`（パッケージディレクトリ）
- [ ] **相対パス禁止**: `"core/templates"` のような相対パスは使うな
- [ ] **テスト**: 新規venvでpip installしてテスト必須

---

## 実行順序

```
→ 1_investigate/symptom.md
→ 1_investigate/scope.md
→ 2_fix/backup.md
→ 2_fix/migration.md
→ 2_fix/apply.md
→ 3_verify/verify.md
→ 4_report/github.md
```

---

## 禁止
- 本番DBへの直接UPDATE/DELETE
- バックアップなしの修正
