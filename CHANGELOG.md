# Changelog

All notable changes to this project will be documented in this file.

## [0.1.12] - 2025-12-29

### Fixed
- `/api/health` エンドポイントのルート順序修正

## [0.1.11] - 2025-12-29

### Fixed
- `focomy createuser` で user.yaml 自動生成

### Added
- `/api/health` ヘルスチェックエンドポイント

## [0.1.10] - 2025-12-29

### Fixed
- `/search`, `/category`, `/archive` ルートに `site` 変数追加

## [0.1.9] - 2025-12-29

### Fixed
- テンプレートに `now` 関数追加
- `psycopg2-binary` 依存追加（migrate用）

## [0.1.8] - 2025-12-29

### Added
- `focomy update --sync` で不足ファイルを同期

## [0.1.7] - 2025-12-29

### Fixed
- テンプレートに `site` 変数追加（全ページエラー修正）
- `focomy makemigrations` のAlembic自動初期化

## [0.1.6] - 2025-12-29

### Fixed
- `focomy validate` のイテレーションエラー修正

## [0.1.5] - 2025-12-29

### Fixed
- Jinja2 `date` フィルター追加
- `user` コンテンツタイプ追加（createuser修正）
- `focomy migrate` のAlembic設定エラー修正

## [0.1.4] - 2025-12-29

### Fixed
- デフォルトテーマのテンプレート名修正（index.html → home.html）
- 欠落テンプレート追加（category.html, archive.html, search.html）

## [0.1.3] - 2025-12-29

### Fixed
- cache_serviceの非同期メソッドにawait追加（coroutineエラー修正）

## [0.1.2] - 2025-12-29

### Fixed
- テンプレートパスをパッケージ内絶対パスに変更

## [0.1.1] - 2025-12-28

### Fixed
- PyPIパッケージでサーバー起動できない問題を修正

## [0.1.0] - 2025-12-28

### Added
- Initial release
- Metadata-driven CMS core (Entity, Field, Relation)
- Admin UI with HTMX + Tailwind
- Editor.js integration for block-based content
- SEO features (JSON-LD, OGP, sitemap, RSS/Atom)
- Authentication (email/password, OAuth, TOTP)
- Media management with image optimization
- Theme system with inheritance
- Plugin system with sandboxing
- CLI (`focomy init`, `focomy serve`, `focomy migrate`)
- pip installable package
- Fly.io deployment support
