# ルート順序修正

## 問題
- `/admin/import`, `/admin/system` が404
- 原因: `/{type_name}`動的ルートより後に定義

## やること
1. `routes.py` 2182-2451行を切り取り
2. 1668行（`# === Entity List ===`）の前に貼り付け
3. 構文チェック
4. サーバー起動テスト
5. `/admin/system`, `/admin/import` アクセス確認

## 完了条件
- [ ] 両ルートが200返却

## 次 → `1_api.md` or 完了
