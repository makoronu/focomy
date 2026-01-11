# デプロイ

**PyPI + Fly.io への公開**

---

## 必須ルール
- 勝手にデプロイ禁止
- ステップ失敗 → 即停止 → 報告 → 指示待ち
- 代替手段・回避策禁止

---

## 実行順序

### 1. 準備
```
→ 1_prepare/version.md
→ 1_prepare/changelog.md
```

### 2. ビルド
```
→ 2_build/test.md
→ 2_build/build.md
```

### 3. ユーザー確認（公開前必須）

```
【デプロイ確認】
- バージョン: x.x.x
- 変更内容: [概要]

デプロイしてよいですか？
```

**承認を得るまで次に進まない**

### 4. 公開
```
→ 3_publish/pypi.md
→ 3_publish/fly.md
```

### 5. 検証
```
→ 4_verify/pip_test.md
→ 4_verify/log.md
```

### 6. テスト依頼
```
→ 5_test_request/test_request.md
```

---

## 完了時

```bash
afplay /System/Library/Sounds/Glass.aiff
```

```
━━━━━━━━━━━━━━━━━━━━
【デプロイ】完了
━━━━━━━━━━━━━━━━━━━━
✓ PyPI: focomy x.x.x
✓ Fly.io: focomy-cms

【次】→ 4_retrospective/_main.md
━━━━━━━━━━━━━━━━━━━━
```
