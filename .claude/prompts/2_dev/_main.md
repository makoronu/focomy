# 開発（大プロンプト）

**このファイルを読んだら、以下の順序で小工程を実行せよ。スキップ禁止。**

---

## 必須ルール（逸脱防止）

1. **各小工程の冒頭で「現在位置: X/Y.md」を出力せよ**
2. **問題発生時 → 即停止 → ユーザーに報告 → 指示を待て**
3. **開発完了後 → 必ず `3_deploy/_main.md` へ進め（本番反映必須）**

---

## 実行順序

### 0. ロードマップ
```
→ ../0_roadmap/start.md  ← タスク着手確認
```

### 1. 準備（中プロンプト）
```
→ 1_prepare/session.md
→ 1_prepare/plan.md      ← 計画提示・承認取得
→ 1_prepare/backup.md
→ 1_prepare/schema.md
→ 1_prepare/architecture.md ← アーキテクチャ境界チェック
→ 1_prepare/design.md    ← 設計原則チェック
→ 1_prepare/api.md       ← API設計チェック
→ 1_prepare/existing.md
```

### 2. 実装（中プロンプト）
```
→ 2_implement/implement.md
→ 2_implement/anti_pattern.md  ← 禁止事項チェック
→ 2_implement/error.md         ← エラー処理チェック
→ 2_implement/security.md      ← セキュリティチェック
→ 2_implement/reuse.md         ← 共通処理チェック
→ 2_implement/audit.md         ← 監査ログチェック
→ 2_implement/type_check.md
→ 2_implement/quality.md
```

### 3. テスト（中プロンプト）
```
→ 3_test/unit.md         ← ユニットテスト
→ 3_test/selenium.md     ← 問題あれば即停止
→ 3_test/doc_update.md
```

### 4. 完了（中プロンプト）
```
→ 4_complete/commit.md
→ 4_complete/schema_update.md
→ 4_complete/log.md
```

---

## 完了時

全工程完了後、以下を実行：

```bash
afplay /System/Library/Sounds/Glass.aiff
```

報告フォーマット：
```
━━━━━━━━━━━━━━━━━━━━
【開発】完了
━━━━━━━━━━━━━━━━━━━━
✓ 準備
✓ 実装
✓ テスト
✓ 完了

【成果物】
- コミット: [hash] "[message]"

【次のステップ】
→ 3_deploy/_main.md（デプロイ必須）
━━━━━━━━━━━━━━━━━━━━
```

---

## 停止条件

- テスト中に問題発見 → 即停止 → 報告
- 判断に迷う → 即停止 → 質問

