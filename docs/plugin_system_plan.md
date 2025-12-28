# Focomy プラグインシステム計画

## 概要

プラグインでFocomyの機能を拡張可能にする。マーケットプレイスの前提となる基盤。

---

## プラグイン種類

| 種類 | 説明 | 例 |
|------|------|-----|
| テーマ | デザインテンプレート | Minimal, Corporate, Blog |
| ブロック | Editor.js カスタムブロック | コードハイライト, 地図埋め込み |
| フィールドタイプ | 新しいフィールド種類 | 色選択, 日付範囲 |
| 認証プロバイダー | OAuth/SSO | LINE, Twitter/X |
| SEO拡張 | SEO機能追加 | 構造化データ自動生成 |
| メディア処理 | 画像/動画処理 | WebP変換, 動画サムネイル |
| 連携 | 外部サービス連携 | Slack通知, Webhook |
| ユーティリティ | その他 | バックアップ, インポート |

---

## ディレクトリ構造

```
focomy/
├── plugins/                    # インストール済みプラグイン
│   ├── focomy-theme-minimal/
│   │   ├── plugin.yaml         # プラグイン定義
│   │   ├── templates/
│   │   └── static/
│   └── focomy-block-code/
│       ├── plugin.yaml
│       └── block.js
└── core/
    └── services/
        └── plugin_loader.py    # プラグインローダー
```

---

## plugin.yaml 仕様

```yaml
name: focomy-theme-minimal
version: 1.0.0
type: theme
label: Minimal Theme
description: シンプルでミニマルなテーマ
author: Focomy Team
homepage: https://github.com/focomy/focomy-theme-minimal
license: MIT

# 依存関係
requires:
  focomy: ">=0.1.0"
  plugins: []

# プラグイン固有設定
config:
  primary_color:
    type: color
    default: "#2563eb"
    label: メインカラー
  show_sidebar:
    type: boolean
    default: true
    label: サイドバー表示

# フック登録
hooks:
  - name: before_render
    handler: hooks.before_render
  - name: after_save
    handler: hooks.after_save

# 静的ファイル
static:
  - src: static/
    dest: /static/plugins/focomy-theme-minimal/

# テンプレート上書き
templates:
  - src: templates/base.html
    dest: themes/minimal/templates/base.html
```

---

## フックシステム

### 利用可能なフック

| フック名 | タイミング | 引数 |
|---------|----------|------|
| `before_render` | テンプレート描画前 | context, template_name |
| `after_render` | テンプレート描画後 | response, context |
| `before_save` | エンティティ保存前 | entity, data |
| `after_save` | エンティティ保存後 | entity |
| `before_delete` | エンティティ削除前 | entity |
| `after_delete` | エンティティ削除後 | entity_id |
| `on_upload` | ファイルアップロード時 | file, metadata |
| `on_login` | ログイン時 | user |
| `on_logout` | ログアウト時 | user |
| `admin_menu` | 管理画面メニュー構築時 | menu_items |
| `api_routes` | APIルート登録時 | router |

### フック実装例

```python
# plugins/focomy-seo-enhanced/hooks.py

def before_render(context: dict, template_name: str) -> dict:
    """SEOメタタグを自動追加"""
    if "entity" in context:
        entity = context["entity"]
        context["seo"] = generate_seo_tags(entity)
    return context

def after_save(entity):
    """保存後にサイトマップ更新"""
    if entity.type in ("post", "page"):
        regenerate_sitemap()
```

---

## プラグインローダー

```python
# core/services/plugin_loader.py

class PluginLoader:
    """プラグインの読み込み・管理"""

    def discover(self) -> list[PluginInfo]:
        """plugins/ 内のプラグインを検出"""

    def load(self, plugin_name: str) -> Plugin:
        """プラグインを読み込み"""

    def enable(self, plugin_name: str) -> None:
        """プラグインを有効化"""

    def disable(self, plugin_name: str) -> None:
        """プラグインを無効化"""

    def install_from_url(self, url: str) -> PluginInfo:
        """URLからプラグインをインストール"""

    def install_from_zip(self, zip_path: Path) -> PluginInfo:
        """ZIPファイルからインストール"""

    def uninstall(self, plugin_name: str) -> None:
        """プラグインをアンインストール"""
```

---

## Admin UI

### プラグイン管理画面 `/admin/plugins`

- インストール済みプラグイン一覧
- 有効/無効切り替え
- 設定画面へのリンク
- アンインストール

### プラグインインストール `/admin/plugins/install`

- URLからインストール
- ZIPアップロード
- （将来）マーケットプレイス連携

### プラグイン設定 `/admin/plugins/{name}/settings`

- plugin.yaml の config に基づく設定フォーム
- 自動生成

---

## セキュリティ

### サンドボックス

- プラグインは限定的なAPIのみアクセス可能
- ファイルシステムアクセス制限
- ネットワークアクセスは明示的許可が必要

### 審査（マーケットプレイス向け）

1. 自動セキュリティスキャン
2. コードレビュー（有料プラグイン）
3. マルウェア検出
4. 依存関係チェック

---

## インストールフロー

```
1. ユーザーがURLまたはZIPを指定
2. プラグインをダウンロード/展開
3. plugin.yaml を検証
4. 依存関係チェック
5. plugins/ にコピー
6. DB に installed_plugins レコード作成
7. フック登録
8. 静的ファイル配置
9. （必要なら）マイグレーション実行
```

---

## CLI コマンド

```bash
# プラグイン一覧
focomy plugin list

# インストール
focomy plugin install <url-or-path>

# 有効化/無効化
focomy plugin enable <name>
focomy plugin disable <name>

# アンインストール
focomy plugin uninstall <name>

# 設定表示
focomy plugin config <name>
```

---

## 実装優先度

| Phase | 内容 |
|-------|------|
| 1 | PluginLoader基盤、plugin.yaml パース |
| 2 | フックシステム |
| 3 | テーマプラグイン対応 |
| 4 | Admin UI（一覧・有効化） |
| 5 | インストール機能（ZIP/URL） |
| 6 | CLI コマンド |
| 7 | ブロック・フィールドタイプ対応 |
| 8 | マーケットプレイス連携 |

---

## 次のステップ

プラグインシステムの前に、まず公式テーマを数種類用意：

1. **Default** - 現在のテーマを整理
2. **Minimal** - シンプル・ミニマル
3. **Corporate** - 企業サイト向け
4. **Blog** - ブログ特化
