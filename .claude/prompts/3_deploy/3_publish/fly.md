# Fly.ioデプロイ

## やること
1. 初回 → fly_setup.md
2. 再デプロイ → `fly deploy`
3. スキーマ変更時 → fly_setup.md 参照

## 失敗時
即停止 → 報告 → 指示待ち

## 完了条件
- `fly deploy` 成功
- `curl https://focomy-cms.fly.dev/health` → OK

## 次 → ../4_verify/pip_test.md
