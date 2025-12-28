# Focomy - 世界一美しいCMS 設計書

## 設計哲学

**「美しい設計が全てを決める」**

- メタデータ駆動
- 重複コードゼロ
- リレーションシップ完璧
- 無駄のない拡張性

---

## 技術スタック

| 項目 | 技術 |
|------|------|
| バックエンド | FastAPI |
| データベース | PostgreSQL + asyncpg |
| ORM | SQLAlchemy (async) |
| テンプレート | Jinja2 |
| フロントエンド | HTMX |
| エディタ | Editor.js |
| CSS | CSS Variables + テーマシステム |
| 認証 | bcrypt + セッション + OAuth |
| デプロイ | Docker / Fly.io / Render |

---

## コアコンセプト：3つの抽象

全ては3つの概念で表現される。

### 1. Entity（エンティティ）

**全てのコンテンツは Entity**

```
Post      → Entity (type: post)
Page      → Entity (type: page)
Contact   → Entity (type: contact)
Property  → Entity (type: property)
User      → Entity (type: user)
Category  → Entity (type: category)
MenuItem  → Entity (type: menu_item)
Widget    → Entity (type: widget)
Comment   → Entity (type: comment)
Redirect  → Entity (type: redirect)
```

PostテーブルもPageテーブルも存在しない。**entitiesテーブル1つで全て管理**。

### 2. Field（フィールド）

**フィールドはメタデータで定義**

テーブルにカラムを追加しない。YAMLで定義し、values テーブルに保存。

```yaml
# content_types/post.yaml
name: post
label: 投稿
path_prefix: /blog
fields:
  - name: title
    type: string
    required: true
    indexed: true
  - name: slug
    type: slug
    unique: true
    auto_generate: title
  - name: body
    type: blocks
  - name: excerpt
    type: text
    max_length: 200
  - name: featured_image
    type: media
  - name: status
    type: select
    options: [draft, published, private]
    default: draft
  - name: published_at
    type: datetime
  # SEO fields
  - name: seo_title
    type: string
  - name: seo_description
    type: text
  - name: seo_noindex
    type: boolean
  - name: seo_nofollow
    type: boolean
  - name: seo_canonical
    type: url
  - name: og_title
    type: string
  - name: og_description
    type: text
  - name: og_image
    type: media
```

### 3. Relation（リレーション）

**リレーションは第一級市民**

外部キーをベタ書きしない。リレーション定義で管理。

```yaml
# relations.yaml
post_categories:
  from: post
  to: category
  type: many_to_many
  label: カテゴリ

post_author:
  from: post
  to: user
  type: many_to_one
  required: true
  label: 著者

comment_post:
  from: comment
  to: post
  type: many_to_one
  required: true
  label: 投稿

menu_item_parent:
  from: menu_item
  to: menu_item
  type: many_to_one
  self_referential: true
  label: 親メニュー
```

---

## データベース設計

### コアテーブル

```sql
-- エンティティ（全コンテンツの親）
CREATE TABLE entities (
    id TEXT PRIMARY KEY,           -- UUID
    type TEXT NOT NULL,            -- post, page, user, etc.
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ,        -- 論理削除
    created_by TEXT,               -- 監査
    updated_by TEXT                -- 監査
);

-- フィールド値（EAVだが最適化済み）
CREATE TABLE entity_values (
    id SERIAL PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id),
    field_name TEXT NOT NULL,
    value_text TEXT,               -- string, text, slug
    value_int INTEGER,             -- integer, boolean
    value_float REAL,              -- float
    value_datetime TIMESTAMPTZ,    -- datetime
    value_json JSONB,              -- blocks, array, object
    UNIQUE(entity_id, field_name)
);

-- リレーション
CREATE TABLE relations (
    id SERIAL PRIMARY KEY,
    from_entity_id TEXT NOT NULL REFERENCES entities(id),
    to_entity_id TEXT NOT NULL REFERENCES entities(id),
    relation_type TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(from_entity_id, to_entity_id, relation_type)
);

-- メディア
CREATE TABLE media (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    width INTEGER,
    height INTEGER,
    alt_text TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT
);

-- ユーザー認証
CREATE TABLE user_auth (
    entity_id TEXT PRIMARY KEY REFERENCES entities(id),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    totp_secret TEXT,
    last_login TIMESTAMPTZ,
    login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMPTZ
);

-- セッション
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES entities(id),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

-- ログイン履歴
CREATE TABLE login_log (
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    ip_address TEXT,
    user_agent TEXT,
    success BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL
);
```

---

## 実装済み機能

### SEO機能

| 機能 | 説明 |
|------|------|
| メタタグ自動生成 | title, description, canonical |
| OGP | og:title, og:description, og:image, og:site_name, og:locale |
| Twitter Card | twitter:card, twitter:site, twitter:creator |
| JSON-LD | Article, WebPage, Organization, WebSite, BreadcrumbList, FAQPage, Person |
| サイトマップ | sitemap.xml 動的生成 |
| robots.txt | 動的生成 |
| RSS/Atom/JSON Feed | /feed.xml, /atom.xml, /feed.json |
| ページ別SEO設定 | noindex/nofollow, canonical上書き, OGP個別設定 |
| パンくずリスト | BreadcrumbList JSON-LD付き |

### セキュリティ

| ヘッダー | 設定値 |
|---------|--------|
| Strict-Transport-Security | max-age=31536000; includeSubDomains |
| Content-Security-Policy | default-src 'self'; script-src... (ページ別に最適化) |
| X-Content-Type-Options | nosniff |
| X-Frame-Options | SAMEORIGIN |
| X-XSS-Protection | 1; mode=block |
| Referrer-Policy | strict-origin-when-cross-origin |
| Permissions-Policy | camera=(), microphone=(), geolocation=()... |
| Cross-Origin-Opener-Policy | same-origin |
| Cross-Origin-Resource-Policy | same-origin |

### リダイレクト管理

**機能:**
- 完全一致/前方一致/正規表現マッチング
- キャッシュ付き高速リダイレクト
- 管理画面からルール追加/編集/削除
- テスト機能

### メニュー管理

**機能:**
- ヘッダー/フッター/サイドバー別メニュー
- 階層構造（ドロップダウン）対応
- ドラッグ&ドロップ並び替え
- YAML設定との併用

### ウィジェット

**ウィジェットタイプ:**
- 最近の投稿
- カテゴリ一覧
- 検索ボックス
- カスタムHTML
- アーカイブ
- タグクラウド

### コメント

**機能:**
- 承認制コメント
- ハニーポットスパム対策
- レート制限（5回/分）
- 管理画面から一括承認/拒否
- ネスト返信対応

### Content Builder（ACF的機能）

WordPress の Advanced Custom Fields に相当する機能。

**高度なフィールドタイプ:**

| タイプ | 説明 |
|--------|------|
| repeater | 繰り返しフィールド（無限ネスト対応） |
| flexible_content | 柔軟なレイアウトブロック |
| group | フィールドグループ |
| gallery | 画像ギャラリー |
| link | リンク（URL + テキスト + target） |
| google_map | Google Maps 座標 |
| date_range | 日付範囲 |
| color | カラーピッカー |
| oembed | 埋め込みコンテンツ |
| taxonomy | カテゴリ/タグ選択 |
| user | ユーザー選択 |
| post_object | 投稿選択 |
| page_link | ページリンク |

**計算フィールド（Formula）:**

```yaml
- name: total_price
  type: formula
  expression: "price * quantity * (1 + tax_rate)"
  dependencies: [price, quantity, tax_rate]
```

**ワークフロー:**

```yaml
workflows:
  review_flow:
    states: [draft, pending_review, approved, published]
    transitions:
      - from: draft
        to: pending_review
        roles: [author, editor]
      - from: pending_review
        to: approved
        roles: [editor, admin]
```

**スケジュール公開:**
- 予約投稿/非公開
- 公開期間設定（開始日〜終了日）
- バックグラウンドワーカーで自動実行

**編集ロック:**
- 他ユーザーが編集中の場合は警告表示
- 5分間のロック期限
- 強制ロック解除機能

### WordPress インポート

WordPress からの完全移行をサポート。

**機能:**

| 機能 | 説明 |
|------|------|
| WXR Parser | WordPress eXtended RSS 形式の解析 |
| コンテンツ移行 | 投稿、固定ページ、カテゴリ、タグ |
| メディア移行 | 画像ダウンロード + WebP変換 |
| ACF変換 | Advanced Custom Fields → Focomy フィールド |
| リダイレクト生成 | 旧URL → 新URL の301リダイレクト |

**使用方法:**

```python
from core.wordpress import WordPressImporter

importer = WordPressImporter(db, entity_service, media_service)
result = await importer.import_from_file(
    "export.xml",
    download_media=True,
    generate_redirects=True,
    convert_acf=True
)
```

### プラグインシステム

WordPress ライクなプラグイン機構。

**プラグイン構造:**

```
plugins/
└── my-plugin/
    ├── plugin.yaml      # メタデータ
    ├── __init__.py      # エントリーポイント
    └── ...
```

**plugin.yaml:**

```yaml
name: my-plugin
version: 1.0.0
description: My awesome plugin
author: Your Name
requires_focomy: ">=1.0.0"
```

**フック/フィルターシステム:**

```python
from core.plugins import hooks

# アクション（副作用）
@hooks.action("post_saved")
async def on_post_saved(entity, is_new):
    # 投稿保存時の処理

# フィルター（値の変換）
@hooks.filter("post_content")
async def modify_content(content):
    return content.replace("foo", "bar")

# 手動呼び出し
await hooks.do_action("post_saved", entity, True)
result = await hooks.apply_filters("post_content", original)
```

**ビルトインフック:**

| フック | タイプ | 説明 |
|--------|--------|------|
| entity_created | action | エンティティ作成時 |
| entity_updated | action | エンティティ更新時 |
| entity_deleted | action | エンティティ削除時 |
| before_render | filter | テンプレートレンダリング前 |
| admin_menu | filter | 管理メニュー構築時 |
| seo_meta | filter | SEOメタタグ生成時 |

### テーマシステム

**ローカルテーマ管理:**

```python
from core.themes import ThemeManager

manager = ThemeManager(themes_dir)
manager.activate("my-theme")
theme = manager.get_active_theme()
```

**テーママーケットプレイス:**

```python
from core.themes import ThemeMarketplace

marketplace = ThemeMarketplace(theme_manager)

# 検索
results = await marketplace.search("blog", category="business")

# インストール
result = await marketplace.install("theme-id", license_key="...")

# アップデートチェック
updates = await marketplace.check_updates(installed_themes)
```

**テーマカスタマイザー:**

```python
from core.themes import ThemeCustomizer

customizer = ThemeCustomizer(theme_manager, settings_service)

# ライブプレビュー
preview_css = await customizer.generate_preview_css({
    "primary_color": "#3b82f6",
    "font_family": "Noto Sans JP"
})

# 設定保存
await customizer.save_customization(theme_id, settings)
```

### パフォーマンス最適化

| 機能 | 説明 |
|------|------|
| 外部CSS | /css/theme.css (Cache-Control: max-age=86400) |
| CSS Minify | 本文CSSは圧縮して配信 |
| Lazy Loading | 画像に loading="lazy" |
| Preload | 重要リソースのpreload |
| DNS Prefetch | 外部ドメインのdns-prefetch |
| Gzip | GZipMiddleware (1000bytes以上) |

### ツール

| ツール | 説明 |
|--------|------|
| リンク検証 | 壊れた内部/外部リンク検出 |
| 孤立ページ検出 | リンクされていないページ検出 |
| サイトマップUI | URL一覧、除外設定、再生成 |

---

## ディレクトリ構造

```
focomy/
├── core/
│   ├── __init__.py
│   ├── main.py                 # FastAPIエントリー + ミドルウェア
│   ├── config.py               # 設定（Pydantic）
│   ├── database.py             # DB接続（asyncpg）
│   ├── rate_limit.py           # レート制限
│   ├── models/
│   │   ├── __init__.py
│   │   ├── entity.py           # Entity, EntityValue
│   │   ├── relation.py         # Relation
│   │   ├── media.py            # Media
│   │   └── auth.py             # UserAuth, Session, LoginLog
│   ├── services/
│   │   ├── __init__.py
│   │   ├── entity.py           # EntityService
│   │   ├── relation.py         # RelationService
│   │   ├── field.py            # FieldService（高度なフィールド対応）
│   │   ├── formula.py          # FormulaService（計算フィールド）
│   │   ├── workflow.py         # WorkflowService
│   │   ├── schedule.py         # ScheduleService（予約投稿）
│   │   ├── edit_lock.py        # EditLockService
│   │   ├── media.py            # MediaService
│   │   ├── auth.py             # AuthService
│   │   ├── seo.py              # SEOService
│   │   ├── theme.py            # ThemeService
│   │   ├── menu.py             # MenuService
│   │   ├── widget.py           # WidgetService
│   │   ├── comment.py          # CommentService
│   │   ├── redirect.py         # RedirectService
│   │   ├── link_validator.py   # LinkValidatorService
│   │   ├── settings.py         # SettingsService
│   │   ├── oauth.py            # OAuthService
│   │   └── cache.py            # CacheService
│   ├── api/
│   │   ├── __init__.py
│   │   ├── entities.py         # /api/entities/*
│   │   ├── relations.py        # /api/*/relations/*
│   │   ├── media.py            # /api/media/*
│   │   ├── auth.py             # /api/auth/*
│   │   ├── schema.py           # /api/schema/*
│   │   ├── seo.py              # /api/seo/* (sitemap, feed)
│   │   ├── comments.py         # /api/comments/*
│   │   ├── forms.py            # /forms/*
│   │   └── revisions.py        # /api/revisions/*
│   ├── admin/
│   │   ├── __init__.py
│   │   └── routes.py           # 管理画面ルート
│   ├── engine/
│   │   ├── __init__.py
│   │   └── routes.py           # フロントエンドルート
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── base.py             # Plugin基底クラス
│   │   ├── hooks.py            # フック/フィルターシステム
│   │   ├── loader.py           # プラグインローダー
│   │   └── manager.py          # プラグインマネージャー
│   ├── themes/
│   │   ├── __init__.py
│   │   ├── manager.py          # テーマ管理
│   │   ├── marketplace.py      # マーケットプレイス連携
│   │   └── customizer.py       # テーマカスタマイザー
│   ├── wordpress/
│   │   ├── __init__.py
│   │   ├── wxr_parser.py       # WXR形式パーサー
│   │   ├── analyzer.py         # コンテンツ分析
│   │   ├── media.py            # メディアインポート
│   │   ├── acf.py              # ACFコンバーター
│   │   ├── redirects.py        # リダイレクト生成
│   │   └── importer.py         # メインインポーター
│   └── templates/
│       └── admin/
│           ├── base.html
│           ├── dashboard.html
│           ├── entity_list.html
│           ├── entity_form.html
│           ├── media.html
│           ├── menus.html
│           ├── widgets.html
│           ├── comments.html
│           ├── settings.html
│           ├── redirects.html
│           ├── link_validator.html
│           ├── sitemap.html
│           └── login.html
├── plugins/                     # ユーザープラグイン
│   └── hello-world/            # サンプルプラグイン
├── content_types/
│   ├── post.yaml
│   ├── page.yaml
│   ├── category.yaml
│   ├── user.yaml
│   ├── menu_item.yaml
│   ├── widget.yaml
│   ├── comment.yaml
│   ├── redirect.yaml
│   └── site_setting.yaml
├── relations.yaml
├── themes/
│   └── default/
│       ├── templates/
│       │   ├── base.html
│       │   ├── index.html
│       │   ├── post.html
│       │   ├── page.html
│       │   ├── category.html
│       │   ├── archive.html
│       │   ├── search.html
│       │   ├── 404.html
│       │   └── 500.html
│       └── theme.yaml
├── static/
│   ├── favicon.ico
│   ├── favicon.svg
│   └── apple-touch-icon.png
├── uploads/
├── config.yaml
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── fly.toml
├── render.yaml
└── docs/
    └── ROADMAP.md
```

---

## デプロイ

### Docker

```bash
docker-compose up -d
```

### Fly.io

```bash
fly launch
fly postgres create --name focomy-db
fly postgres attach focomy-db
fly secrets set FOCOMY_SECRET_KEY="your-secret-key"
fly deploy
```

### 環境変数

| 変数 | 説明 |
|------|------|
| FOCOMY_DATABASE_URL | PostgreSQL接続URL |
| FOCOMY_SECRET_KEY | セッション暗号化キー |
| FOCOMY_DEBUG | デバッグモード（true/false） |

---

## API設計

### REST API

```
# エンティティCRUD
GET    /api/entities/{type}
POST   /api/entities/{type}
GET    /api/entities/{type}/{id}
PUT    /api/entities/{type}/{id}
DELETE /api/entities/{type}/{id}

# リレーション
GET    /api/entities/{type}/{id}/relations/{relation_type}
POST   /api/entities/{type}/{id}/relations/{relation_type}
DELETE /api/entities/{type}/{id}/relations/{relation_type}/{to_id}

# メディア
POST   /api/media
GET    /api/media/{id}
DELETE /api/media/{id}

# 認証
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me
GET    /api/auth/google/login
GET    /api/auth/google/callback

# スキーマ
GET    /api/schema
GET    /api/schema/{type}
GET    /api/schema/relations

# コメント
POST   /api/comments
PUT    /api/comments/{id}/moderate
DELETE /api/comments/{id}

# リビジョン
GET    /api/entities/{type}/{id}/revisions
POST   /api/entities/{type}/{id}/revisions/{revision_id}/restore
```

### フロントエンドルート

```
/                              # ホーム（最新投稿）
/{type}/{slug}                 # 単一表示
/category/{slug}               # カテゴリアーカイブ
/archive/{year}/{month}        # 月別アーカイブ
/search                        # 検索

# SEO
/sitemap.xml                   # サイトマップ
/robots.txt                    # robots.txt
/feed.xml                      # RSS 2.0
/atom.xml                      # Atom
/feed.json                     # JSON Feed
/manifest.json                 # PWA Manifest

# アセット
/css/theme.css                 # テーマCSS（キャッシュ付き）
/static/*                      # 静的ファイル
/uploads/*                     # アップロードファイル
```

### 管理画面URL

```
/admin                         # ダッシュボード
/admin/{type}                  # エンティティ一覧
/admin/{type}/new              # 新規作成
/admin/{type}/{id}/edit        # 編集
/admin/media                   # メディア管理
/admin/menus                   # メニュー管理
/admin/widgets                 # ウィジェット管理
/admin/comments                # コメント管理
/admin/settings                # サイト設定
/admin/redirects               # リダイレクト管理
/admin/tools/sitemap           # サイトマップ管理
/admin/tools/link-validator    # リンク検証
```

---

## 設定

### config.yaml

```yaml
site:
  name: "My Site"
  tagline: "A beautiful CMS"
  url: "https://example.com"
  language: "ja"
  timezone: "Asia/Tokyo"

admin:
  path: "/admin"
  per_page: 20

media:
  upload_dir: "uploads"
  max_size: 10485760
  allowed_types:
    - image/jpeg
    - image/png
    - image/gif
    - image/webp
    - application/pdf
  image:
    max_width: 1920
    max_height: 1920
    quality: 85
    format: webp

security:
  secret_key: "change-this-in-production"
  session_expire: 86400
  login_attempts: 5
  lockout_duration: 900
  password_min_length: 12
  headers:
    hsts_enabled: true
    hsts_max_age: 31536000
    hsts_include_subdomains: true
    csp_enabled: true
    permissions_policy_enabled: true

oauth:
  google_client_id: ""
  google_client_secret: ""

menus:
  header:
    - label: ホーム
      url: /
    - label: ブログ
      url: /blog
  footer:
    - label: プライバシーポリシー
      url: /page/privacy
```

---

## 美しさの指標

| 指標 | 目標 | 現状 |
|------|------|------|
| コアテーブル数 | 7以下 | 7 |
| サービスクラス数 | 20以下 | 18 |
| APIエンドポイント | 35以下 | 28 |
| 重複コード | 0 | 0 |
| 新コンテンツタイプ追加 | YAML 1ファイルのみ | 達成 |

---

## 完了タスク

| ID | タスク | 完了日 |
|----|--------|--------|
| 001 | プロジェクト基盤構築 | 2025-12-26 |
| 002 | EntityService実装 | 2025-12-26 |
| 003 | RelationService実装 | 2025-12-26 |
| 004 | FieldService実装 | 2025-12-26 |
| 005 | 認証基盤構築 | 2025-12-26 |
| 006 | API実装 | 2025-12-26 |
| 007 | 管理画面基盤 | 2025-12-26 |
| 008 | Editor.js統合 | 2025-12-26 |
| 009 | メディア管理 | 2025-12-26 |
| 010 | SEO自動生成 | 2025-12-26 |
| 011 | テーマシステム | 2025-12-26 |
| 012 | CLI実装 | 2025-12-26 |
| 013 | robots.txt実装 | 2025-12-27 |
| 014 | フィード実装 | 2025-12-27 |
| 015 | ファビコン対応 | 2025-12-27 |
| 016 | SEO設定UI構築 | 2025-12-27 |
| 017 | 構造化データ拡充 | 2025-12-27 |
| 018 | ページ別SEO制御 | 2025-12-27 |
| 019 | パンくず実装 | 2025-12-27 |
| 020 | OGP/Twitter補完 | 2025-12-27 |
| 021 | 外部CSS分離 | 2025-12-27 |
| 022 | パフォーマンス最適化 | 2025-12-27 |
| 023 | リダイレクト管理 | 2025-12-27 |
| 024 | セキュリティヘッダー | 2025-12-27 |
| 025 | リンク検証機能 | 2025-12-27 |
| 026 | サイトマップUI | 2025-12-27 |
| 027 | メニュー管理システム | 2025-12-28 |
| 028 | 柔軟なブログルーティング | 2025-12-28 |
| 029 | 設定管理UI | 2025-12-28 |
| 030 | ウィジェット/サイドバー | 2025-12-28 |
| 031 | コメント機能 | 2025-12-28 |
| 032 | Content Builder（ACF的機能） | 2025-12-28 |
| 033 | WordPress インポート | 2025-12-28 |
| 034 | プラグインシステム | 2025-12-28 |
| 035 | テーママーケットプレイス | 2025-12-28 |

---

## 本番環境

| 項目 | 値 |
|------|-----|
| URL | https://focomy-cms.fly.dev |
| プラットフォーム | Fly.io |
| リージョン | nrt（東京） |
| データベース | PostgreSQL（Fly Postgres） |

---

## まとめ

**3つの抽象で全てを表現**

1. Entity（統一エンティティ）
2. Field（メタデータ定義）
3. Relation（リレーション）

**これが世界一美しいCMS。**
