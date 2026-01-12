# pip インストールテスト

## やること
1. 新規venv作成
2. pip install focomy
3. 全機能テスト

## コマンド
```bash
cd /tmp && rm -rf focomy-verify && mkdir focomy-verify && cd focomy-verify
python3 -m venv venv && source venv/bin/activate
pip install focomy
focomy version
focomy init testsite && cd testsite
```

## サーバーテスト（必須）
```bash
# バックグラウンドで起動
focomy serve &
sleep 3

# 各エンドポイント確認
curl -s http://localhost:8000/ | head -5
curl -s http://localhost:8000/admin/login | head -5
curl -s http://localhost:8000/api/health | head -5

# 停止
kill %1
```

## テンプレート確認（必須）
```bash
# focomy init 後に実行
ls themes/default/templates/
# 以下が存在すること:
# - base.html
# - home.html
# - post.html
# - category.html
# - archive.html
# - search.html
```

## アップグレードテスト（必須）
```bash
# 旧バージョンでサイト作成
pip install focomy==前バージョン
focomy init upgrade_test && cd upgrade_test

# アップグレード
pip install --upgrade focomy

# コア機能が壊れていないこと
focomy serve &
sleep 3
curl -s http://localhost:8000/admin/login | head -5
kill %1
```

## 完了条件
- [ ] インストール成功
- [ ] `focomy version` 動作
- [ ] `focomy init` でサイト作成成功
- [ ] **テンプレート6種が全て存在**
- [ ] `focomy serve` でサーバー起動
- [ ] 各エンドポイント応答
- [ ] **pip upgrade後も既存サイトが動作**

## 次 → log.md
