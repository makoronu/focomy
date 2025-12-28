# Focomy

**世界一美しいCMS** - メタデータ駆動 / 重複コードゼロ / リレーション完璧

## 要件

- Python 3.10+
- PostgreSQL 13+

## インストール

```bash
pip install focomy
```

## クイックスタート

```bash
# 1. サイト作成
focomy init mysite
cd mysite

# 2. PostgreSQL データベース作成
createdb mysite

# 3. 初期ユーザー作成
focomy createuser -e admin@example.com -n Admin -r admin

# 4. サーバー起動
focomy serve

# 5. 管理画面にアクセス
open http://localhost:8000/admin
```

## CLI コマンド

| コマンド | 説明 |
|---------|------|
| `focomy init <name>` | 新規サイト作成 |
| `focomy serve` | 開発サーバー起動 |
| `focomy createuser -e <email>` | ユーザー作成 |
| `focomy migrate` | マイグレーション実行 |
| `focomy makemigrations -m "msg"` | マイグレーション生成 |
| `focomy validate` | コンテンツタイプ定義検証 |
| `focomy update` | 最新版に更新 |
| `focomy update --check` | 更新確認のみ |
| `focomy backup` | バックアップ作成 |
| `focomy backup --include-db` | DB含めてバックアップ |
| `focomy restore <file>` | バックアップ復元 |

### createuser オプション

```bash
focomy createuser -e <email> [-n <name>] [-r <role>] [-p <password>]

# -e, --email    : メールアドレス（必須）
# -n, --name     : 表示名（デフォルト: Admin）
# -r, --role     : 権限 admin/editor/author（デフォルト: admin）
# -p, --password : パスワード（省略時は対話入力、12文字以上）
```

### serve オプション

```bash
focomy serve [--host <host>] [--port <port>] [--reload]

# --host   : バインドホスト（デフォルト: 0.0.0.0）
# --port   : ポート番号（デフォルト: 8000）
# --reload : 自動リロード有効
```

## 環境変数

| 変数 | 必須 | 説明 | 例 |
|------|------|------|-----|
| `FOCOMY_DATABASE_URL` | ○ | PostgreSQL接続URL | `postgresql+asyncpg://user:pass@localhost:5432/dbname` |
| `FOCOMY_SECRET_KEY` | ○ | セッション暗号化キー | ランダム文字列（32文字以上推奨） |
| `FOCOMY_DEBUG` | - | デバッグモード | `true` / `false` |

`.env` ファイルで設定可能（`focomy init` で自動生成）

## ディレクトリ構造

```
mysite/
├── .env                 # 環境変数
├── config.yaml          # サイト設定
├── relations.yaml       # リレーション定義
├── content_types/       # コンテンツタイプ定義
│   ├── post.yaml
│   ├── page.yaml
│   └── category.yaml
├── themes/              # テーマ
│   └── default/
├── uploads/             # アップロードファイル
└── static/              # 静的ファイル
```

## 設定ファイル

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

security:
  secret_key: "your-secret-key"
  session_expire: 86400

media:
  upload_dir: "uploads"
  max_size: 10485760
  image:
    max_width: 1920
    quality: 85
    format: webp
```

### コンテンツタイプ定義

`content_types/post.yaml`:

```yaml
name: post
label: 投稿
path_prefix: /blog
fields:
  - name: title
    type: string
    required: true
  - name: slug
    type: slug
    unique: true
  - name: body
    type: blocks
  - name: status
    type: select
    options: [draft, published]
    default: draft
```

### リレーション定義

`relations.yaml`:

```yaml
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
```

## デプロイ

### Fly.io

```bash
fly launch
fly postgres create --name mysite-db
fly postgres attach mysite-db
fly secrets set FOCOMY_SECRET_KEY="your-secret-key"
fly deploy
```

### Docker

```bash
docker-compose up -d
```

## 開発（ソースから）

```bash
git clone https://github.com/makoronu/focomy.git
cd focomy
pip install -e ".[dev]"

# 開発サーバー起動
cd core && uvicorn main:app --reload --port 8000
```

## 設計思想

詳細は [focomy_specification.md](focomy_specification.md) を参照。

**3つの抽象で全てを表現:**

1. **Entity** - 全コンテンツは統一エンティティ
2. **Field** - メタデータ駆動フィールド定義
3. **Relation** - リレーションは第一級市民

## ライセンス

MIT License - [LICENSE](LICENSE)
