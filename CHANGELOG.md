# Changelog

All notable changes to this project will be documented in this file.

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
