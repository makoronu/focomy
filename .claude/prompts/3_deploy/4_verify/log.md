# ログ確認・記録

## やること
1. 本番ログにエラーがないか確認
2. デプロイログ出力

## ログ確認
```bash
ssh -i ~/.ssh/REA.pem root@sas.realestateautomation.net "journalctl -u sas-backend --since '5 minutes ago'"
```

## CLAUDE.md更新
```
| 作業中 | なし |
| 完了 | [デプロイ内容を追加] |
| 最終更新 | YYYY-MM-DD |
```

## 完了条件
- [ ] エラーなし
- [ ] CLAUDE.md更新済み

## 次の工程
→ 終了（大プロンプト完了報告へ）
