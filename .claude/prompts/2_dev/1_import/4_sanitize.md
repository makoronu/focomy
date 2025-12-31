# コンテンツサニタイズ

## 目的
- XSS等のセキュリティリスク排除
- 危険なタグ・属性除去

## やること
1. `ContentSanitizer`作成
2. 除去対象定義（script, iframe, onclick等）
3. インポート時にサニタイズ適用
4. 警告ログ出力

## 参照
- `docs/wordpress_specification.md` セクション1.7（content:encoded）
- `docs/wordpress_import_issues.md` セクション5.3

## 完了条件
- [ ] 危険タグ除去確認
- [ ] 警告がログに記録

## 次 → `5_linkfix.md`
