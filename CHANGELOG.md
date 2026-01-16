# Changelog

All notable changes to this project will be documented in this file.

## [0.1.111] - 2026-01-16

### Fixed
- フォームページで管理バーが表示されない問題を修正
  - forms.pyでrender_templateを使用するよう変更
  - admin context（is_admin, admin_user, content_types等）が正しく注入されるように

## [0.1.110] - 2026-01-16

### Fixed
- form.html render_fieldマクロ定義順序修正
  - Jinja2マクロを使用箇所より前に移動
  - 重複定義（70行）を削除
  - /forms/{slug}ページの500エラー解消

## [0.1.105] - 2026-01-15

### Fixed
- フォーム編集画面のバリデーションエラー修正
  - slugフィールドのpattern属性をChrome unicodeSets対応に修正
  - モーダル内フィールドのrequired属性削除でフォーム送信エラー解消

## [0.1.104] - 2026-01-15

### Fixed
- メニューリンクURL自動生成を修正
  - linked_entity_idなしの場合は一覧ページURLを返すように変更
  - form, news, tag等のlink_typeに対応
  - path_prefixからの動的URL生成をサポート
  - form.yamlにpath_prefix追加で/forms一覧ページ有効化

## [0.1.103] - 2026-01-15

### Fixed
- menu_item.yamlのlink_typeをstring型に変更
  - select型の検証によりform等が500エラーになる問題を修正
  - 任意のmenu_linkableコンテンツタイプをリンク可能に

## [0.1.102] - 2026-01-15

### Fixed
- メニューリンクタイプを動的生成に変更
  - ContentTypeにmenu_linkable属性追加
  - フォーム、ニュース、タグ等全7種がメニューからリンク可能に

## [0.1.101] - 2026-01-15

### Fixed
- サイドバーメニューを動的生成に変更
  - ハードコードメニュー項目を削除
  - content_typesメタデータからadmin_menu=trueのエンティティを動的表示

## [0.1.100] - 2026-01-15

### Added
- ビジュアルフォームビルダー機能
  - フォーム編集画面でGUIベースのフィールド編集が可能に
  - フィールド追加/編集/削除
  - ドラッグ&ドロップによる並び替え（SortableJS）
  - 対応フィールドタイプ: text, email, tel, textarea, select, radio, checkbox
  - select/radio用の選択肢エディタ
  - 既存のfields_config JSONとの後方互換性維持

## [0.1.99] - 2026-01-14

### Fixed
- メニューのYAMLフォールバック削除
  - DB項目のみ表示（yaml_* IDの謎項目が消える）
  - Import from YAML機能は維持

## [0.1.98] - 2026-01-14

### Fixed
- 手動アップデート「既に最新」でも自動再起動するよう修正
- UIメッセージを「数秒後にページを更新してください」に変更

## [0.1.97] - 2026-01-14

### Added
- 手動アップデート後の自動再起動機能
  - pip upgrade完了後、2秒待機してPM2/systemctlで自動再起動
  - HTTPレスポンス送信後にバックグラウンドで実行

## [0.1.96] - 2026-01-14

### Fixed
- メニューDelete機能の正しいエラーハンドリング実装
  - YAML項目削除時: 400エラー + ユーザー向けメッセージ表示
  - 存在しないID: 404エラー + メッセージ表示
  - HTMXエラーハンドラー追加でToast通知
  - Deleteボタンを全項目で表示（v0.1.95の誤修正を取り消し）

## [0.1.95] - 2026-01-14

### Fixed
- メニューLink Typeからpost/category削除（channel/series主体に整理）

## [0.1.94] - 2026-01-14

### Added
- メニューにチャンネル/シリーズリンクタイプ追加
  - menu_item.yaml: `channel`, `series` オプション追加
  - menu.py: `/channel/{slug}`, `/series/{slug}` URL解決追加
  - menus.html: UI選択肢追加
- ウィジェットにチャンネル/シリーズ一覧追加
  - widget.yaml: `channel_list`, `series_list` オプション追加
  - widget.py: ChannelListWidget, SeriesListWidget クラス追加

## [0.1.93] - 2026-01-14

### Added
- 手動アップデート機能
  - システム情報ページに「手動アップデート」ボタン追加
  - `/admin/api/update-execute` エンドポイント追加
  - UpdateService.execute_update() メソッド追加

### Fixed
- 「更新をチェック」ボタンがJSONを表示する問題を修正
  - HTML形式でレスポンスを返すように変更（HTMX対応）

## [0.1.92] - 2026-01-14

### Added
- チャンネル一覧テンプレート `channel.html` 新規作成
- シリーズ一覧テンプレート `series.html` 新規作成

### Fixed
- `/channel/{slug}` および `/series/{slug}` ルートが404になる問題を修正
  - テンプレートが存在しなかったため追加
- チャンネル/シリーズルートでメニュー・ウィジェットが表示されない問題を修正
  - `render_theme()` ラッパー経由に変更し、コンテキスト統一

## [0.1.91] - 2026-01-14

### Fixed
- /admin/menus 500エラーを修正
  - Jinja2マクロ`render_menu_items`が使用箇所より後に定義されていた
  - マクロ定義を使用箇所より前に移動

## [0.1.90] - 2026-01-14

### Fixed
- 一括操作（bulk action）が404エラーになる問題を修正
  - FastAPIルート順序問題: `/{type_name}/bulk`が`/{type_name}/{entity_id}`より後に定義されていた
  - "bulk"がentity_idとして解釈され、エンティティが見つからず404
  - `/{type_name}/bulk`ルートを`/{type_name}/{entity_id}`より前に移動

## [0.1.89] - 2026-01-13

### Fixed
- 一括操作（削除・下書き戻し等）がチャンネル経由で動作しない問題
  - `AdminURL.entity_bulk()` が常に正しいルート形式を返すよう修正
- menus/widgets ページのエラーハンドリング追加
  - 500エラー発生時もページを表示、ログ出力

## [0.1.88] - 2026-01-12

### Changed
- コア/ユーザー層分離アーキテクチャ
  - content_types/relations.yamlを`core/`に移動（単一情報源）
  - FieldServiceの読み込みロジック刷新（コアは常にパッケージから）
  - focomy initでcontent_types/をコピーしない
  - プラグインは追加のみ、コア上書き禁止

### Fixed
- pip upgrade後に既存サイトが壊れる問題を根本解決

## [0.1.67] - 2026-01-11

### Fixed
- テーマテンプレートフォールバック追加
  - 非defaultテーマで不足テンプレートをdefaultから継承
  - theme_inheritance サービスを ThemeService に統合

## [0.1.66] - 2026-01-11

### Fixed
- CSP: Google Fonts (fonts.googleapis.com) を style-src に追加

## [0.1.65] - 2026-01-11

### Fixed
- _get_all_yaml_settingsにthemeが含まれていないバグを修正

## [0.1.64] - 2026-01-11

### Fixed
- config.yamlのtheme設定がget_settings()で読み込まれないバグを修正

## [0.1.63] - 2026-01-11

### Fixed
- テーマ・メニューのYAMLフォールバック設定追加
  - config.yaml に theme/menus セクション追加
  - ThemeConfig クラス追加
  - settings.py の config_map に "theme" 追加
  - DB未設定時でもテーマ/メニューが表示されるように

## [0.1.62] - 2026-01-11

### Changed
- メニュー・ウィジェット機能を有効化（config.yaml features.menu/widget = true）

## [0.1.57] - 2026-01-03

### Added
- エディタUX改善（128-S1-A4）
  - 見出しレベル選択ドロップダウン（インラインツールバーからH1-H6選択）
  - スラッシュコマンド（/入力でブロック選択メニュー表示）
  - 右クリックでインラインツールバー表示

## [0.1.56] - 2026-01-03

### Fixed
- バージョン読み込み修正（pyproject.toml優先）

## [0.1.55] - 2026-01-02

### Fixed
- バージョン表示がハードコードされている問題修正（#100）
  - importlib.metadataから動的にバージョン取得
  - core/__init__.py, cli.py, main.py, login.html統一

## [0.1.54] - 2026-01-02

### Added
- プレビュー機能強化（105）
  - 分割画面リアルタイムプレビュー（エディタ|プレビュー並列表示）
  - レイアウト切替（エディタのみ/分割/プレビューのみ）
  - レスポンシブプレビュー（Desktop/Tablet/Mobile幅切替）
  - デバウンス付きプレビュー更新（300ms）
  - localStorage状態保持（リロード後も設定維持）
  - プレビューAPI（POST /admin/api/preview/render）

## [0.1.53] - 2026-01-02

### Added
- エディタUX改善（103+104）
  - コードエディタ切替（Visual/JSON表示切替）
  - Ctrl+S / Cmd+S キーボードショートカット保存

## [0.1.52] - 2026-01-02

### Fixed
- インラインツールがツールバーに表示されない問題修正（102）
  - インラインツール定義を`tools`オブジェクト内に移動

## [0.1.51] - 2026-01-02

### Added
- インラインツール拡充（102）
  - Strikethrough（取り消し線）
  - TextColorInlineTool（選択テキスト文字色）
  - HighlightInlineTool（選択テキストハイライト色）
- theme.py: s/spanタグ許可、style属性のセキュアサニタイズ

## [0.1.50] - 2026-01-02

### Added
- BlockTune: 配置機能追加（100）
  - AlignmentBlockTune（左揃え・中央揃え・右揃え）
  - paragraph/headerブロックに適用
- BlockTune: テキスト色・背景色追加（101）
  - ColorBlockTune（文字色・背景色のカラーピッカー）
  - paragraph/headerブロックに適用

## [0.1.49] - 2026-01-02

### Added
- Editor.jsブロック追加（095-099）
  - 見出しh1-h6対応（levels拡張）
  - ギャラリーブロック（複数画像グリッド）
  - カバーブロック（背景画像+オーバーレイテキスト）
  - グループブロック（背景色+パディング）
  - スペーサーブロック（可変高さ余白）

## [0.1.48] - 2026-01-02

### Fixed
- パスワード更新クエリのカラム名修正
  - UserAuth.user_id → UserAuth.entity_id

## [0.1.47] - 2026-01-02

### Fixed
- パスワード更新が機能しない問題修正
  - user_authテーブルへの直接更新に変更
  - ユーザー作成時のUserAuthレコード作成対応

## [0.1.46] - 2026-01-02

### Fixed
- ユーザー管理UI修正
  - admin_hiddenフィールドが編集画面に表示される問題修正
  - パスワードフィールドがハッシュ表示される問題修正
  - パスワード保存時の自動ハッシュ化対応

## [0.1.45] - 2026-01-02

### Changed
- 編集画面フィールド整理 (#092)
  - OGフィールド削除（og_title, og_description, og_image）
  - 抜粋フィールド非表示化（admin_hidden: true）

## [0.1.44] - 2026-01-01

### Added
- WordPress Import: Analyzeボタンにローディングスピナー追加 (#52)

## [0.1.43] - 2026-01-01

### Fixed
- WordPress Import: Dry-Runで`value_string`属性エラー修正 (#51)
  - `EntityValue.value_string` → `EntityValue.value_text`

## [0.1.42] - 2026-01-01

### Fixed
- WordPress Import: Dry-RunでAttributeError修正 (#51)
  - `_find_by_slug`メソッドを追加（存在しない`entity_svc.find_by_slug`を置換）

## [0.1.41] - 2026-01-01

### Fixed
- WordPress Import: Dry-Run結果が全件0になる問題修正 (#51)
  - APIレスポンス構造をJavaScriptの期待する形式に変換

## [0.1.40] - 2026-01-01

### Fixed
- Admin: entity_list.htmlでinteger型フィールドにtruncateフィルタ適用時のエラー修正 (#50)

## [0.1.39] - 2026-01-01

### Changed
- Protocol: ENUM削除（10クラス）→ 文字列定数クラスに変換
  - Permission, Role, ImportJobStatus, ImportJobPhase, PluginState
  - ThemeState, SettingType, ConfigSource, DeploymentState
- Protocol: 重複コード共通化（parse_form_fields関数追加）

## [0.1.38] - 2026-01-01

### Added
- WordPress Import: 全ルートにrequire_feature("wordpress_import")追加

### Changed
- Feature Flags: wordpress_import機能をデフォルト有効化

### Fixed
- Admin: 全エンティティページでcontent_type/list_fieldsをmodel_dump()変換（Jinja2互換性修正）
- Protocol: 例外握りつぶし修正（channel取得時のログ出力追加）
- Protocol: per_pageハードコード修正（config.yamlから取得）

## [0.1.37] - 2026-01-01

### Changed
- Feature Flags: link_validator機能をデフォルト有効化

## [0.1.36] - 2026-01-01

### Added
- ブログチャンネル・シリーズアーキテクチャ
- content_types: blog.yaml（チャンネル管理）
- content_types: series.yaml（シリーズ管理）
- チャンネル別投稿管理（/admin/channel/{slug}/posts）
- チャンネル別RSSフィード（/blog/{channel}/feed.xml）

### Fixed
- Dashboard: admin_menuフィルター適用、ContentType→dict変換 (#44)
- Series: チャンネル選択UIのリレーション設定 (#45)
- RSS: feedgenからraw XML生成に変更 (#46)
- Channel Posts: list_fields/search_query追加 (#47)

### Changed
- post.yaml: admin_menu: false（チャンネル別管理に移行）

## [0.1.35] - 2026-01-01

### Fixed
- Admin: サイドバーにタグリンク追加 (#43)

## [0.1.34] - 2026-01-01

### Fixed
- scaffold: tag.yamlにadmin_menu: true追加（サイドバー表示修正）

## [0.1.33] - 2026-01-01

### Added
- content_types: tag.yaml追加（WordPress Import用wp_id付き）
- content_types: category.yamlにwp_id, wp_parent_idフィールド追加

## [0.1.32] - 2026-01-01

### Fixed
- Audit: Entity CRUD操作の監査ログ記録問題修正 (#41)
- Phase 4完了: search/revision/audit全機能正常動作確認

## [0.1.31] - 2026-01-01

### Changed
- Feature Flags: audit機能をデフォルト有効化（Phase 4完了）

## [0.1.30] - 2026-01-01

### Changed
- Feature Flags: revision機能をデフォルト有効化

## [0.1.29] - 2026-01-01

### Changed
- Feature Flags: search機能をデフォルト有効化（Phase 4開始）

## [0.1.28] - 2026-01-01

### Fixed
- Admin: imageタイプフィールドもファイルアップロード処理対象に追加 (#40)

## [0.1.27] - 2026-01-01

### Fixed
- Admin: mediaタイプフィールドのファイルアップロード処理追加 (#40)

## [0.1.26] - 2026-01-01

### Changed
- Feature Flags: media機能をデフォルト有効化（Phase 2開始）

## [0.1.25] - 2026-01-01

### Fixed
- EntityService: create()/update()後のvalues relationshipロード問題修正 (#38)
- CLI: `focomy update --sync` で既存content_typesに新フィールドをマージ (#38)

## [0.1.24] - 2026-01-01

### Fixed
- FieldService: scaffoldへのフォールバック追加（pip install時にcontent_typesが見つからない問題） (#38)

## [0.1.23] - 2026-01-01

### Fixed
- CLI createuser: --passwordオプション復活（指定時は使用、未指定時はgetpass） (#36)
- Scaffold: post.yaml/page.yamlにSEOフィールド追加（seo_title, seo_description等） (#38)
- Admin: POST削除エンドポイントでリダイレクト返却 (#39)

## [0.1.22] - 2026-01-01

### Fixed
- CLI createuser: 全例外キャッチでエラーメッセージ表示 (#36)
- Admin: POST /admin/{type}/{id}/delete エンドポイント追加 (#39)

## [0.1.21] - 2026-01-01

### Fixed
- CLI createuser: --passwordオプション削除、常にgetpassを使用 (#36)
- RBAC: Entity.get()エラー修正（serializeを追加） (#37)
- Search API: トランザクションabort時のrollback追加 (#35)

## [0.1.20] - 2026-01-01

### Added
- 機能フラグシステム実装（Phase 0）
- FeaturesConfig設定クラス
- `is_feature_enabled()`, `require_feature()` ヘルパー関数
- STABILIZATION_PLAN.md（機能安定化計画）

### Changed
- APIルーターの条件付き登録（機能フラグに基づく）
- 管理画面ルートにフラグチェック追加（media, widget, menu, link_validator）

## [0.1.19] - 2025-12-31

### Fixed
- import_jobsテーブルの不足カラム追加（dry_run_result, checkpoint等）

## [0.1.18] - 2025-12-31

### Fixed
- WordPress Import: source_typeバリデーションエラー修正 (#5)

## [0.1.17] - 2025-12-31

### Fixed
- beautifulsoup4 (bs4) を依存関係に追加 (#4)

## [0.1.16] - 2025-12-31

### Fixed
- user_authテーブルの不足カラム追加（reset_token, totp_enabled等）

## [0.1.15] - 2025-12-31

### Added
- WordPress Import: ドライラン機能（実インポート前のシミュレーション）
- WordPress Import: プレビュー機能（3件試しインポート→確定/破棄）
- WordPress Import: インポート検証機能（整合性チェック、SEO監査）
- WordPress Import: 内部リンク自動修正（WordPress→Focomy URL変換）
- WordPress Import: リダイレクト生成（nginx/Apache/.htaccess/JSON/YAML）

### Changed
- WordPress Import: XSSサニタイズ強化（危険タグ・属性の除去）

### Fixed
- 管理画面ナビゲーションにインポートリンク追加 (#2)

## [0.1.13] - 2025-12-30

### Changed
- メディアストレージをフラット構造に変更（`uploads/001_filename.webp`）
- 命名規則を連番+元名に統一（通常アップロード・WordPress Import共通）

### Added
- WordPress Import機能（WXR/REST API対応）
- WebP変換オプション
- `file_hash`カラム追加（重複検知用）
- category/tag/media/menuコンテンツタイプ

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
