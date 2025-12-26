# 本番パス確認

## やること
本番サーバーの実際のパスを確認

## コマンド
```bash
ssh -i ~/.ssh/REA.pem root@sas.realestateautomation.net "systemctl status sas-backend | grep WorkingDirectory"
ssh -i ~/.ssh/REA.pem root@sas.realestateautomation.net "systemctl status sas-frontend | grep WorkingDirectory"
```

## 確認ポイント
- ドキュメントのパスと一致しているか
- 不一致あれば先に解決

## 完了条件
- [ ] 本番パス確認した

## 次の工程
→ backup.md
