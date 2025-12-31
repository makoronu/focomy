# 内部リンク修正

## 目的
- WPのURLをFocomyのURLに書き換え
- リンク切れ防止

## やること
1. URLマッピング生成（旧→新）
2. `InternalLinkFixer`作成
3. コンテンツ内のhref, src書き換え
4. 修正ログ出力

## 参照
- `docs/wordpress_specification.md` セクション5（URL構造）
- `docs/wordpress_import_plan.md` セクション3.5

## 完了条件
- [ ] 内部リンクが新URLに変換
- [ ] 修正件数がログに記録

## 次 → `5a_redirect.md`
