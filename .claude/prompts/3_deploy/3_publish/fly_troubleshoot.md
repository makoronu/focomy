# Fly.io トラブルシューティング

## DB接続エラー
1. `fly postgres list` でDB状態確認
2. 停止中 → `fly machine restart -a focomy-db`

## 環境変数エラー
1. `fly secrets list` で確認
2. `FOCOMY_` prefix 忘れてないか

## 次 → fly.md
