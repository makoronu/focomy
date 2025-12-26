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
| データベース | SQLite + FTS5 |
| ORM | SQLAlchemy |
| テンプレート | Jinja2 |
| フロントエンド | HTMX |
| エディタ | Editor.js |
| CSS | Tailwind CSS |
| 認証 | bcrypt + TOTP |

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
```

PostテーブルもPageテーブルも存在しない。**entitiesテーブル1つで全て管理**。

### 2. Field（フィールド）

**フィールドはメタデータで定義**

テーブルにカラムを追加しない。YAMLで定義し、values テーブルに保存。

```yaml
# content_types/post.yaml
name: post
label: 投稿
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

post_related:
  from: post
  to: post
  type: many_to_many
  label: 関連記事
```

---

## データベース設計

### コアテーブル（これだけ）

```sql
-- エンティティ（全コンテンツの親）
CREATE TABLE entities (
    id TEXT PRIMARY KEY,           -- UUID
    type TEXT NOT NULL,            -- post, page, user, etc.
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at DATETIME,           -- 論理削除
    created_by TEXT,               -- 監査
    updated_by TEXT                -- 監査
);
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_deleted ON entities(deleted_at);

-- フィールド値（EAVだが最適化済み）
CREATE TABLE entity_values (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    value_text TEXT,               -- string, text, slug
    value_int INTEGER,             -- integer, boolean
    value_float REAL,              -- float
    value_datetime DATETIME,       -- datetime
    value_json JSON,               -- blocks, array, object
    FOREIGN KEY (entity_id) REFERENCES entities(id),
    UNIQUE(entity_id, field_name)
);
CREATE INDEX idx_values_entity ON entity_values(entity_id);
CREATE INDEX idx_values_field ON entity_values(field_name);
CREATE INDEX idx_values_text ON entity_values(value_text) WHERE value_text IS NOT NULL;
CREATE INDEX idx_values_int ON entity_values(value_int) WHERE value_int IS NOT NULL;

-- リレーション
CREATE TABLE relations (
    id INTEGER PRIMARY KEY,
    from_entity_id TEXT NOT NULL,
    to_entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,   -- post_categories, post_author, etc.
    sort_order INTEGER DEFAULT 0,
    metadata JSON,                 -- リレーション固有のメタデータ
    created_at DATETIME NOT NULL,
    FOREIGN KEY (from_entity_id) REFERENCES entities(id),
    FOREIGN KEY (to_entity_id) REFERENCES entities(id),
    UNIQUE(from_entity_id, to_entity_id, relation_type)
);
CREATE INDEX idx_relations_from ON relations(from_entity_id);
CREATE INDEX idx_relations_to ON relations(to_entity_id);
CREATE INDEX idx_relations_type ON relations(relation_type);

-- 全文検索
CREATE VIRTUAL TABLE entities_fts USING fts5(
    entity_id,
    content,
    content='entity_values',
    content_rowid='id'
);

-- メディア（アップロードファイル）
CREATE TABLE media (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,        -- 元ファイル名
    stored_path TEXT NOT NULL,     -- 保存パス
    mime_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    width INTEGER,                 -- 画像の場合
    height INTEGER,                -- 画像の場合
    alt_text TEXT,
    created_at DATETIME NOT NULL,
    created_by TEXT
);

-- ユーザー認証（特別扱い：セキュリティ上）
CREATE TABLE user_auth (
    entity_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    totp_secret TEXT,
    last_login DATETIME,
    login_attempts INTEGER DEFAULT 0,
    locked_until DATETIME,
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- ログイン履歴
CREATE TABLE login_log (
    id INTEGER PRIMARY KEY,
    user_id TEXT,
    ip_address TEXT,
    user_agent TEXT,
    success BOOLEAN,
    created_at DATETIME NOT NULL
);

-- セッション
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES entities(id)
);
```

### なぜEAV？

WordPress の wp_postmeta がクソなのは設計が悪いから。正しく設計されたEAVは美しい。

**最適化ポイント：**
1. 型別カラム（value_text, value_int, value_float, value_datetime, value_json）
2. 適切なインデックス
3. 複合ユニーク制約
4. FTS5との連携

---

## サービス設計（重複コードゼロ）

### EntityService（唯一のCRUD）

```python
class EntityService:
    """全エンティティを統一的に操作"""

    async def create(self, type: str, data: dict, user_id: str = None) -> Entity:
        """エンティティ作成"""
        pass

    async def update(self, id: str, data: dict, user_id: str = None) -> Entity:
        """エンティティ更新"""
        pass

    async def delete(self, id: str, user_id: str = None) -> bool:
        """論理削除"""
        pass

    async def get(self, id: str) -> Entity:
        """単一取得"""
        pass

    async def find(self, type: str, query: QueryParams) -> List[Entity]:
        """検索"""
        pass

    async def count(self, type: str, query: QueryParams) -> int:
        """件数"""
        pass
```

**PostService、PageService、ContactService は存在しない。**

### RelationService（リレーション操作）

```python
class RelationService:
    """リレーション操作"""

    async def attach(self, from_id: str, to_id: str, relation_type: str) -> Relation:
        """リレーション追加"""
        pass

    async def detach(self, from_id: str, to_id: str, relation_type: str) -> bool:
        """リレーション削除"""
        pass

    async def sync(self, from_id: str, to_ids: List[str], relation_type: str) -> List[Relation]:
        """リレーション同期（差分更新）"""
        pass

    async def get_related(self, entity_id: str, relation_type: str) -> List[Entity]:
        """関連エンティティ取得"""
        pass
```

### FieldService（フィールド定義管理）

```python
class FieldService:
    """フィールド定義のロード・バリデーション"""

    def get_content_type(self, type: str) -> ContentType:
        """コンテンツタイプ定義取得"""
        pass

    def validate(self, type: str, data: dict) -> ValidationResult:
        """フィールドバリデーション"""
        pass

    def serialize(self, entity: Entity) -> dict:
        """エンティティをJSONにシリアライズ"""
        pass
```

---

## API設計（統一エンドポイント）

### REST API

```
# エンティティCRUD（全コンテンツタイプ共通）
GET    /api/entities/{type}           # 一覧
POST   /api/entities/{type}           # 作成
GET    /api/entities/{type}/{id}      # 取得
PUT    /api/entities/{type}/{id}      # 更新
DELETE /api/entities/{type}/{id}      # 削除

# リレーション
GET    /api/entities/{type}/{id}/relations/{relation_type}  # 関連取得
POST   /api/entities/{type}/{id}/relations/{relation_type}  # 関連追加
DELETE /api/entities/{type}/{id}/relations/{relation_type}/{to_id}  # 関連削除

# メディア
POST   /api/media                     # アップロード
GET    /api/media/{id}                # 取得
DELETE /api/media/{id}                # 削除

# 認証
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me

# スキーマ（メタデータ）
GET    /api/schema                    # 全コンテンツタイプ定義
GET    /api/schema/{type}             # 特定タイプの定義
GET    /api/schema/relations          # リレーション定義
```

### クエリパラメータ

```
# フィルタ
?filter[status]=published
?filter[created_at][gte]=2025-01-01

# ソート
?sort=-created_at        # 降順
?sort=title              # 昇順

# ページネーション
?page=1&per_page=20

# フィールド選択
?fields=id,title,slug

# リレーション展開
?include=author,categories
```

---

## ディレクトリ構造

```
focomy/
├── core/
│   ├── __init__.py
│   ├── main.py                 # FastAPIエントリー
│   ├── config.py               # 設定
│   ├── database.py             # DB接続
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
│   │   ├── field.py            # FieldService
│   │   ├── media.py            # MediaService
│   │   └── auth.py             # AuthService
│   ├── api/
│   │   ├── __init__.py
│   │   ├── entities.py         # /api/entities/*
│   │   ├── relations.py        # /api/*/relations/*
│   │   ├── media.py            # /api/media/*
│   │   ├── auth.py             # /api/auth/*
│   │   └── schema.py           # /api/schema/*
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── routes.py           # 管理画面ルート
│   │   └── views/              # HTMX用ビュー
│   ├── engine/
│   │   ├── __init__.py
│   │   └── renderer.py         # テンプレートレンダリング
│   └── seo/
│       ├── __init__.py
│       └── generator.py        # SEO自動生成
├── content_types/              # コンテンツタイプ定義
│   ├── post.yaml
│   ├── page.yaml
│   ├── category.yaml
│   └── user.yaml
├── relations.yaml              # リレーション定義
├── themes/
│   └── default/
│       ├── templates/
│       │   ├── admin/
│       │   │   ├── base.html
│       │   │   ├── dashboard.html
│       │   │   ├── entity_list.html
│       │   │   └── entity_form.html
│       │   └── public/
│       │       ├── base.html
│       │       ├── index.html
│       │       ├── single.html
│       │       └── archive.html
│       ├── static/
│       │   ├── css/
│       │   └── js/
│       └── theme.yaml
├── plugins/                    # プラグイン（content_type追加）
├── uploads/                    # アップロードファイル
├── config.yaml                 # サイト設定
├── cli.py                      # CLIツール
└── requirements.txt
```

---

## コンテンツタイプ定義例

### post.yaml

```yaml
name: post
label: 投稿
label_plural: 投稿一覧
icon: document
admin_menu: true
searchable: true

fields:
  - name: title
    type: string
    label: タイトル
    required: true
    indexed: true
    max_length: 200

  - name: slug
    type: slug
    label: スラッグ
    unique: true
    auto_generate: title

  - name: body
    type: blocks
    label: 本文

  - name: excerpt
    type: text
    label: 抜粋
    max_length: 200
    auto_generate: body  # 本文から自動生成

  - name: featured_image
    type: media
    label: アイキャッチ
    accept: image/*

  - name: status
    type: select
    label: ステータス
    options:
      - value: draft
        label: 下書き
      - value: published
        label: 公開
      - value: private
        label: 非公開
    default: draft

  - name: published_at
    type: datetime
    label: 公開日時

relations:
  - type: post_author
    label: 著者
    required: true

  - type: post_categories
    label: カテゴリ
```

### category.yaml

```yaml
name: category
label: カテゴリ
label_plural: カテゴリ一覧
icon: folder
admin_menu: true
hierarchical: true  # 階層構造

fields:
  - name: name
    type: string
    label: 名前
    required: true
    indexed: true

  - name: slug
    type: slug
    label: スラッグ
    unique: true
    auto_generate: name

  - name: description
    type: text
    label: 説明

relations:
  - type: category_parent
    label: 親カテゴリ
    target: category
    self_referential: true
```

### user.yaml

```yaml
name: user
label: ユーザー
label_plural: ユーザー一覧
icon: user
admin_menu: true
auth_entity: true  # 認証用エンティティ

fields:
  - name: name
    type: string
    label: 名前
    required: true

  - name: email
    type: email
    label: メールアドレス
    required: true
    unique: true
    auth_field: true  # 認証に使用

  - name: role
    type: select
    label: 権限
    options:
      - value: admin
        label: 管理者
      - value: editor
        label: 編集者
      - value: author
        label: 投稿者
    default: author

  - name: avatar
    type: media
    label: アバター
    accept: image/*
```

---

## フィールドタイプ一覧

| タイプ | 説明 | 保存先 |
|--------|------|--------|
| string | 短いテキスト | value_text |
| text | 長いテキスト | value_text |
| slug | URLスラッグ | value_text |
| email | メールアドレス | value_text |
| url | URL | value_text |
| integer | 整数 | value_int |
| float | 小数 | value_float |
| boolean | 真偽値 | value_int |
| datetime | 日時 | value_datetime |
| date | 日付 | value_datetime |
| select | 選択肢 | value_text |
| multiselect | 複数選択 | value_json |
| blocks | Editor.jsブロック | value_json |
| media | メディアファイル | value_text (media.id) |
| json | 任意のJSON | value_json |

---

## 拡張性（プラグイン）

プラグインは「新しいcontent_type追加」に過ぎない。

### 不動産プラグイン例

```
plugins/
└── real_estate/
    ├── plugin.yaml
    ├── content_types/
    │   └── property.yaml
    └── relations.yaml
```

```yaml
# plugins/real_estate/content_types/property.yaml
name: property
label: 物件
label_plural: 物件一覧
icon: building
admin_menu: true
searchable: true

fields:
  - name: name
    type: string
    label: 物件名
    required: true

  - name: property_type
    type: select
    label: 物件種別
    options:
      - value: mansion
        label: マンション
      - value: house
        label: 戸建
      - value: land
        label: 土地

  - name: price
    type: integer
    label: 価格
    suffix: 円

  - name: address
    type: string
    label: 住所

  - name: layout
    type: string
    label: 間取り

  - name: area
    type: float
    label: 面積
    suffix: m²

  - name: built_year
    type: integer
    label: 築年

  - name: images
    type: media
    label: 画像
    multiple: true
    accept: image/*

  - name: status
    type: select
    label: ステータス
    options:
      - value: available
        label: 販売中
      - value: contracted
        label: 契約済
      - value: sold
        label: 売却済
```

**これだけで物件管理機能が追加される。コード追加ゼロ。**

---

## セキュリティ

### 認証

- bcryptパスワードハッシュ
- パスワード強度チェック（12文字以上、記号必須）
- ログイン試行制限（5回失敗→15分ロック）
- セッションCookie（secure, httponly, samesite=strict）
- 2段階認証（TOTP）オプション

### 入力処理

- 全入力サニタイズ
- SQLインジェクション対策（SQLAlchemy ORM）
- XSS対策（Jinja2自動エスケープ）
- CSRFトークン

### アップロード

- 拡張子ホワイトリスト
- MIMEタイプ検証
- ファイルサイズ上限
- 画像はWebP変換

### セキュリティヘッダー

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'
Strict-Transport-Security: max-age=31536000
```

---

## 管理画面

HTMX + Jinja2 による管理画面。

### 特徴

- **動的フォーム生成**: content_type定義から自動生成
- **統一リスト画面**: 全コンテンツタイプで同じUI
- **リレーション選択UI**: 自動生成
- **ブロックエディタ**: Editor.js統合

### 管理画面URL

```
/admin/                          # ダッシュボード
/admin/{type}                    # エンティティ一覧
/admin/{type}/new                # 新規作成
/admin/{type}/{id}               # 編集
/admin/media                     # メディア管理
/admin/settings                  # 設定
```

---

## CLI

```bash
# 新規サイト作成
focomy init mysite

# 開発サーバー起動
focomy serve --port 8000

# データベースマイグレーション
focomy migrate

# スキーマ検証
focomy validate

# 静的HTML生成
focomy build --output=dist/

# バックアップ
focomy backup --output=backup.zip

# バージョン確認
focomy version
```

---

## 美しさの指標

| 指標 | 目標 |
|------|------|
| コアテーブル数 | 7以下 |
| サービスクラス数 | 5以下 |
| APIエンドポイント | 15以下 |
| 重複コード | 0 |
| 新コンテンツタイプ追加 | YAML 1ファイルのみ |

---

## まとめ

**3つの抽象で全てを表現**

1. Entity（統一エンティティ）
2. Field（メタデータ定義）
3. Relation（リレーション）

**これが世界一美しいCMS。**
