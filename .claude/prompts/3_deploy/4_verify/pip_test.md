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

## 完了条件
- [ ] インストール成功
- [ ] `focomy version` 動作
- [ ] `focomy init` でサイト作成成功
- [ ] `focomy serve` でサーバー起動
- [ ] `/` トップページ表示
- [ ] `/admin/login` ログイン画面表示（テンプレート解決）
- [ ] `/api/health` ヘルスチェック応答

## 次 → log.md
