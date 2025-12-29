# PyPI公開

## やること

### 1. 認証確認
```bash
# 環境変数が設定されているか確認
echo $TWINE_USERNAME
```
- 未設定 → pypi_setup.md でトークン取得

### 2. 公開
```bash
TWINE_USERNAME=__token__ TWINE_PASSWORD=<token> twine upload dist/*
```

### 3. エラー時
- 認証エラー → ユーザーにトークン確認
- その他 → pypi_setup.md 参照

## 完了条件
- [ ] https://pypi.org/project/focomy/ で新バージョン確認

## 次 → fly.md
