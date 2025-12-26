# 検証（大プロンプト）

**大きな変更前にのみ実行。通常の開発では不要。**

---

## 実行条件
- 新機能追加
- 大規模リファクタリング
- 構造変更

---

## 実行順序

### 1. 調査（中プロンプト）
```
→ 1_investigate/structure.md
→ 1_investigate/screenshot.md
→ 1_investigate/ux.md
→ 1_investigate/code.md
```

### 2. 分析（中プロンプト）
```
→ 2_analyze/why.md
→ 2_analyze/duplicate.md
→ 2_analyze/metadata.md
```

### 3. 判定（中プロンプト）
```
→ 3_decide/decision.md
→ 3_decide/report.md
```

---

## 完了時

```bash
afplay /System/Library/Sounds/Glass.aiff
```

報告フォーマット：
```
━━━━━━━━━━━━━━━━━━━━
【検証】完了
━━━━━━━━━━━━━━━━━━━━
✓ 調査
✓ 分析
✓ 判定

【発見した問題】
- X件

【判定結果】
パッチ修正可能 / 部分再設計 / 全体再設計

【確認事項】
この判定で進めてよいですか？
━━━━━━━━━━━━━━━━━━━━
```

---

## 重要

**このフェーズではコード変更禁止。観察と分析のみ。**
