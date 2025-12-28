# PyPI公開

## 事前確認
- [ ] PyPIアカウント設定済み (~/.pypirc or TWINE_*)
- [ ] ユーザー承認「公開してよい」

---

## 初回公開（アカウント未作成の場合）

### 1. アカウント作成
1. https://pypi.org/account/register/ でアカウント作成
2. メール認証

### 2. 2FA有効化（必須）
1. https://pypi.org/manage/account/two-factor/
2. Authenticatorアプリで設定

### 3. APIトークン発行
1. https://pypi.org/manage/account/token/
2. スコープ: 全プロジェクト または 特定プロジェクト
3. トークンをコピー（`pypi-` で始まる）

### 4. 認証設定
```bash
# 方法A: 環境変数
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-xxxxx

# 方法B: ~/.pypirc
cat > ~/.pypirc << 'EOF'
[pypi]
username = __token__
password = pypi-xxxxx
EOF
chmod 600 ~/.pypirc
```

---

## 公開

### TestPyPI（テスト）
```bash
twine upload --repository testpypi dist/*
```

### 本番PyPI
```bash
twine upload dist/*
```

---

## 完了条件
- [ ] PyPIにアップロード成功
- [ ] https://pypi.org/project/focomy/ でパッケージ確認

## トラブルシューティング
- 403 Forbidden → 2FAが有効化されていない、またはトークンが無効
- duplicate file → バージョン番号を上げる必要あり

## 次 → fly.md
