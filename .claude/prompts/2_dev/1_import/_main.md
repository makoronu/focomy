# インポート機能修正

## 参照（必読）
- `docs/wordpress_specification.md` ← **WordPress仕様**
- `docs/wordpress_import_issues.md` ← 問題点・修正計画
- `docs/wordpress_import_plan.md` ← 設計詳細

## フロー

```
0_route_fix → 1_api → 2_dryrun → 2a_preview → 2b_checkpoint
→ 2c_diff → 3_rollback → 4_sanitize → 5_linkfix → 5a_redirect
→ 6_verify → 完了
```

## 分岐
| 作業 | ファイル |
|------|---------|
| ルート順序修正 | `0_route_fix.md` |
| API改善 | `1_api.md` |
| ドライラン | `2_dryrun.md` |
| プレビュー | `2a_preview.md` |
| チェックポイント | `2b_checkpoint.md` |
| 差分インポート | `2c_diff.md` |
| ロールバック | `3_rollback.md` |
| サニタイズ | `4_sanitize.md` |
| 内部リンク修正 | `5_linkfix.md` |
| リダイレクト生成 | `5a_redirect.md` |
| 検証 | `6_verify.md` |
