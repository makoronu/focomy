# コード品質チェック

## チェックリスト
- [ ] any型なし
- [ ] ハードコードなし
- [ ] 共通ユーティリティ使用
- [ ] エラーがUIに通知される
- [ ] API応答がJSON形式

## 確認方法
```bash
# any型検索
grep -r ": any" frontend/src/

# ハードコード検索
grep -rE "localhost|:8000|:3002" frontend/src/
```

## 完了条件
- [ ] 全チェック項目OK

## 中断条件
- 1つでもNG → 修正してから次へ

## 次の工程
→ ../3_test/selenium.md
