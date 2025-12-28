# PyPI公開

## 事前確認
- [ ] PyPIアカウント設定済み (~/.pypirc or TWINE_*)
- [ ] ユーザー承認「公開してよい」

## コマンド
```bash
# テスト公開（TestPyPI）
twine upload --repository testpypi dist/*

# 本番公開
twine upload dist/*
```

## 完了条件
- [ ] PyPIにアップロード成功

## 次 → fly.md
