# デバッグ（大プロンプト）

**本番バグ発生時に使用。プロトコル準拠で修正。**

---

## 実行順序

```
→ 1_investigate/symptom.md
→ 1_investigate/scope.md
→ 2_fix/backup.md
→ 2_fix/migration.md
→ 2_fix/apply.md
→ 3_verify/verify.md
```

---

## 禁止
- 本番DBへの直接UPDATE/DELETE
- バックアップなしの修正
