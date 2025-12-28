# ビルド

## やること
1. dist/ クリア
2. パッケージビルド

## コマンド
```bash
rm -rf dist/
python -m build
```

## 確認
- dist/focomy-x.x.x.tar.gz
- dist/focomy-x.x.x-py3-none-any.whl

## 完了条件
- [ ] wheel と sdist 生成
- [ ] ビルドエラーなし

## 注意事項

### pyproject.toml の force-include
`[tool.hatch.build.targets.wheel.force-include]` と `packages = ["core"]` を同時に使うと **ファイル重複エラー** が発生する。

```toml
# NG: 重複する
[tool.hatch.build.targets.wheel]
packages = ["core"]

[tool.hatch.build.targets.wheel.force-include]
"core/templates" = "core/templates"  # 既にpackagesで含まれる
```

```toml
# OK: packagesのみ使用
[tool.hatch.build.targets.wheel]
packages = ["core"]
# force-includeは使わない（packagesで自動的にサブディレクトリも含まれる）
```

## 次 → ../3_publish/pypi.md
