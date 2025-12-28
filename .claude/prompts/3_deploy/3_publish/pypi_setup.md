# PyPI 初回セットアップ

## やること
1. https://pypi.org/account/register/ でアカウント作成
2. 2FA有効化（必須）
3. APIトークン発行
4. 認証設定（下記どちらか）

## 認証設定
```bash
# 環境変数
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-xxxxx
```

## 完了条件
- [ ] `twine upload` が認証通る

## 次 → pypi.md
