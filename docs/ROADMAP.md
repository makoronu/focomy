# ROADMAP

## 参照

- [設計書](../focomy_specification.md)

## 進行中

| ID | タスク | 開始日 |
|----|--------|--------|
| 018 | ページ別SEO制御 | 2025-12-27 |

## 予定

| ID | タスク | 優先度 | 依存 |
|----|--------|--------|------|
| 017 | 構造化データ拡充 | 高 | 010 |
| 018 | ページ別SEO制御 | 高 | 016 |
| 019 | パンくず実装 | 中 | 017 |
| 020 | OGP/Twitter補完 | 高 | 016 |
| 021 | 外部CSS分離 | 中 | 011 |
| 022 | パフォーマンス最適化 | 中 | 021 |
| 023 | リダイレクト管理 | 中 | 006 |
| 024 | セキュリティヘッダー | 中 | - |
| 025 | リンク検証機能 | 低 | 006 |
| 026 | サイトマップUI | 低 | 013 |

### 001 詳細

#### 概要
ディレクトリ構造、依存関係、DB初期化、コンテンツタイプ定義

#### 成果物
```
focomy/
├── core/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   ├── services/
│   └── api/
├── content_types/
│   ├── post.yaml
│   ├── page.yaml
│   ├── category.yaml
│   └── user.yaml
├── relations.yaml
├── themes/default/
├── config.yaml
└── requirements.txt
```

#### DB
- entities
- entity_values
- relations
- media
- user_auth
- sessions
- login_log

### 002 詳細

#### 概要
統一CRUDサービス実装

#### メソッド
- create(type, data, user_id)
- update(id, data, user_id)
- delete(id, user_id)
- get(id)
- find(type, query)
- count(type, query)

### 003 詳細

#### 概要
リレーション操作サービス

#### メソッド
- attach(from_id, to_id, relation_type)
- detach(from_id, to_id, relation_type)
- sync(from_id, to_ids, relation_type)
- get_related(entity_id, relation_type)

### 004 詳細

#### 概要
フィールド定義ロード・バリデーション

#### メソッド
- get_content_type(type)
- get_all_content_types()
- validate(type, data)
- serialize(entity)

### 005 詳細

#### 概要
認証・セッション管理

#### 機能
- ログイン/ログアウト
- セッション管理
- パスワードハッシュ
- ログイン試行制限

### 006 詳細

#### 概要
REST API実装

#### エンドポイント
- /api/entities/{type}
- /api/entities/{type}/{id}
- /api/entities/{type}/{id}/relations/{relation_type}
- /api/media
- /api/auth/*
- /api/schema

### 007 詳細

#### 概要
HTMX + Jinja2管理画面

#### 画面
- ダッシュボード
- エンティティ一覧（動的生成）
- エンティティ編集（動的フォーム）
- メディア管理

### 008 詳細

#### 概要
ブロックエディタ統合

#### ブロック
- paragraph, header, list
- image, quote, table
- code, raw, embed

### 009 詳細

#### 概要
画像アップロード・変換

#### 処理
- WebP変換
- リサイズ（長辺1920px）
- 日付フォルダ保存
- SHA256ファイル名

### 010 詳細

#### 概要
SEOメタデータ自動生成

#### 自動生成
- title, description
- OGP
- JSON-LD
- sitemap.xml

### 011 詳細

#### 概要
テーマ・テンプレート

#### 機能
- CSS変数
- テンプレート継承
- カスタムCSS

### 012 詳細

#### 概要
CLIツール

#### コマンド
- focomy serve
- focomy migrate
- focomy validate
- focomy build

### 013 詳細

#### 概要
robots.txt動的生成

#### 成果物
- /robots.txt ルート
- sitemap参照
- Disallow設定

### 014 詳細

#### 概要
RSS/Atom/JSONフィード

#### 成果物
- /feed.xml (RSS 2.0)
- /atom.xml
- /feed.json

### 015 詳細

#### 概要
ファビコン複数サイズ

#### 成果物
- favicon.ico
- apple-touch-icon
- manifest.json
- theme-color

### 016 詳細

#### 概要
SEO設定管理画面

#### 成果物
- サイトタイトル
- デフォルト説明
- OGP画像
- GA4/Search Console

### 017 詳細

#### 概要
JSON-LD拡充

#### 成果物
- Organization
- WebSite+SearchAction
- Person (著者)
- FAQPage

### 018 詳細

#### 概要
ページ別SEO設定

#### 成果物
- noindex/nofollow
- canonical上書き
- OGP個別設定

### 019 詳細

#### 概要
パンくずナビ

#### 成果物
- BreadcrumbList JSON-LD
- テンプレートヘルパー

### 020 詳細

#### 概要
OGP/Twitter完全対応

#### 成果物
- og:site_name/locale
- article:published_time
- twitter:site/creator

### 021 詳細

#### 概要
CSS外部ファイル化

#### 成果物
- /static/css/theme.css
- キャッシュヘッダー

### 022 詳細

#### 概要
パフォーマンス最適化

#### 成果物
- lazy loading
- preload/prefetch
- CSS/JS minify

### 023 詳細

#### 概要
リダイレクト管理

#### 成果物
- 301管理UI
- リダイレクトルール

### 024 詳細

#### 概要
セキュリティヘッダー

#### 成果物
- HSTS
- CSP
- X-Frame-Options

### 025 詳細

#### 概要
リンク検証機能

#### 成果物
- 壊れたリンク検出
- 孤立ページ検出

### 026 詳細

#### 概要
サイトマップ管理

#### 成果物
- 再生成ボタン
- 除外設定

## 完了

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
