# Focomy 用語定義

## コアコンセプト

### Entity（エンティティ）
すべてのコンテンツの基本単位。記事、ページ、ユーザー、メディアなどすべてがEntityとして統一管理される。

```python
entity = Entity(
    id="uuid",
    type="post",  # content_type.yamlで定義されたタイプ
    created_at=datetime,
    updated_at=datetime,
)
```

### Content Type（コンテンツタイプ）
Entityの種類を定義する設定。`content_types/`ディレクトリのYAMLファイルで定義される。

**正式名称**: Content Type
**略称**: type（コード内での参照時）
**非推奨**: 「コンテンツ種別」「タイプ」単独使用

### Field（フィールド）
Content Typeを構成する個々の項目。テキスト、数値、日時、リレーションなど。

### Relation（リレーション）
Entity間の関係性。多対多、一対多、自己参照などをサポート。

---

## 設定関連

### config.yaml
システム全体の設定ファイル。サーバー設定、DB接続、認証設定など。
**変更頻度**: 低（デプロイ時）
**用途**: インフラ・システム設定

### site_setting
サイト運用に関する設定をDBに保存。サイト名、メタ情報、テーマ設定など。
**変更頻度**: 高（管理画面から）
**用途**: サイト運営設定

### 設定の優先順位
1. 環境変数（最優先）
2. DB（site_setting）
3. YAML（config.yaml）
4. デフォルト値

```
ENV > DB > YAML > Default
```

---

## ファイル・ディレクトリ

| 名称 | パス | 説明 |
|------|------|------|
| content_types | `/content_types/*.yaml` | エンティティ定義 |
| relations | `/relations.yaml` | リレーション定義 |
| themes | `/themes/{name}/` | テーマファイル |
| plugins | `/plugins/{name}/` | プラグインファイル |
| uploads | `/uploads/` | アップロードメディア |

---

## ユーザー・権限

| 用語 | 説明 |
|------|------|
| User | 管理画面にログインできるユーザー |
| Role | 権限の集合（admin, editor, author） |
| Permission | 個別の操作権限（create, read, update, delete） |

### ロール階層
```
admin > editor > author
```

---

## ステータス

### Entity Status
| 値 | 日本語 | 説明 |
|----|--------|------|
| draft | 下書き | 非公開 |
| published | 公開 | 公開中 |
| scheduled | 予約 | 指定日時に公開 |
| archived | アーカイブ | 非表示（削除ではない） |

### 論理削除
`deleted_at`がNULLでないEntityは論理削除状態。
**非推奨**: 物理削除（DELETEは使用しない）

---

## API・技術用語

| 用語 | 定義 |
|------|------|
| slug | URLに使用される識別子（例: `my-first-post`） |
| path_prefix | Content Typeの基本URL（例: `/blog`） |
| blocks | Editor.jsの構造化コンテンツ |

---

## 非推奨用語

| 非推奨 | 推奨 | 理由 |
|--------|------|------|
| article | post | 統一のため |
| entry | entity | 正式名称使用 |
| config | settings | 文脈により使い分け |
| delete | soft delete | 論理削除を明示 |

---

## コード規約

### 命名規則
- クラス: PascalCase（`EntityService`）
- 関数: snake_case（`get_entity`）
- 定数: UPPER_SNAKE_CASE（`DEFAULT_LANGUAGE`）
- ファイル: snake_case（`entity_service.py`）

### Content Type参照
```python
# 正しい
type_name = "post"
entity.type == "page"

# 避ける
entity_type = "post"
content_type = "page"
```
