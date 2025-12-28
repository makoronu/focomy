# ビルド

## やること
1. `rm -rf dist/`
2. `python -m build`

## 完了条件
- [ ] dist/*.whl 生成
- [ ] dist/*.tar.gz 生成

## 注意
- pyproject.toml の force-include と packages 併用禁止 → build_note.md

## 次 → ../3_publish/pypi.md
