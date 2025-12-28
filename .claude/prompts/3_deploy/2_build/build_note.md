# ビルド注意事項

## force-include 問題
`packages` と `force-include` 併用でファイル重複エラー

```toml
# NG
[tool.hatch.build.targets.wheel]
packages = ["core"]
[tool.hatch.build.targets.wheel.force-include]
"core/templates" = "core/templates"

# OK
[tool.hatch.build.targets.wheel]
packages = ["core"]
```

## 次 → build.md
