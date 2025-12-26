# デプロイ実行

## 事前確認（必須）
- [ ] ユーザーから「デプロイしてよい」と承認を得たか？
- 承認なし → 停止 → 「デプロイしてよいですか？」と確認

## やること
deploy.shを実行

## コマンド
```bash
./scripts/deploy.sh
```

## deploy.shがやること
1. git push
2. 本番でgit pull
3. 設定ファイル保護・復元
4. npm install && build
5. サービス再起動
6. ヘルスチェック

## 手動デプロイ時（必須）
```bash
# フロントエンド: NEXT_PUBLIC_*はビルド時に埋め込まれる
ssh rea-conoha "cd /opt/SAS/frontend && npm run build && systemctl restart sas-frontend"

# バックエンド
ssh rea-conoha "systemctl restart sas-backend"
```

## 完了条件
- [ ] deploy.sh成功

## 中断条件
- エラー発生 → 停止して報告

## 次の工程
→ ../4_verify/verify.md
