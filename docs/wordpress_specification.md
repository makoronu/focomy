# WordPress 仕様書

WordPress Import機能の実装に必要なWordPress公式仕様をまとめる。

---

## 1. WXR（WordPress eXtended RSS）フォーマット

### 1.1 概要

- **バージョン**: 1.2
- **公式仕様**: なし（リバースエンジニアリングで解読）
- **ベース**: RSS 2.0 + WordPress独自拡張

### 1.2 名前空間

```xml
<rss version="2.0"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:wfw="http://wellformedweb.org/CommentAPI/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
  xmlns:wp="http://wordpress.org/export/1.2/">
```

### 1.3 チャネル要素（サイト情報）

| 要素 | 説明 | 例 |
|------|------|-----|
| `<title>` | サイトタイトル | My Blog |
| `<link>` | サイトURL | https://example.com |
| `<description>` | キャッチフレーズ | Just another WordPress site |
| `<pubDate>` | 作成日時（RFC-822） | Mon, 30 Dec 2024 12:00:00 +0000 |
| `<language>` | 言語コード | ja |
| `<wp:wxr_version>` | WXRバージョン | 1.2 |
| `<wp:base_site_url>` | ホストURL | https://example.com |
| `<wp:base_blog_url>` | ブログURL | https://example.com |

### 1.4 著者要素（wp:author）

```xml
<wp:author>
  <wp:author_id>1</wp:author_id>
  <wp:author_login><![CDATA[admin]]></wp:author_login>
  <wp:author_email><![CDATA[admin@example.com]]></wp:author_email>
  <wp:author_display_name><![CDATA[管理者]]></wp:author_display_name>
  <wp:author_first_name><![CDATA[太郎]]></wp:author_first_name>
  <wp:author_last_name><![CDATA[山田]]></wp:author_last_name>
</wp:author>
```

### 1.5 カテゴリ要素（wp:category）

```xml
<wp:category>
  <wp:term_id>2</wp:term_id>
  <wp:category_nicename><![CDATA[news]]></wp:category_nicename>
  <wp:category_parent><![CDATA[]]></wp:category_parent>
  <wp:cat_name><![CDATA[ニュース]]></wp:cat_name>
</wp:category>
```

### 1.6 タグ要素（wp:tag）

```xml
<wp:tag>
  <wp:term_id>5</wp:term_id>
  <wp:tag_slug><![CDATA[wordpress]]></wp:tag_slug>
  <wp:tag_name><![CDATA[WordPress]]></wp:tag_name>
</wp:tag>
```

### 1.7 投稿/ページ要素（item）

```xml
<item>
  <!-- 標準RSS要素 -->
  <title>投稿タイトル</title>
  <link>https://example.com/post-slug/</link>
  <pubDate>Mon, 30 Dec 2024 12:00:00 +0000</pubDate>
  <dc:creator><![CDATA[admin]]></dc:creator>
  <guid isPermaLink="false">https://example.com/?p=123</guid>
  <description></description>
  <content:encoded><![CDATA[<p>本文HTML</p>]]></content:encoded>
  <excerpt:encoded><![CDATA[抜粋テキスト]]></excerpt:encoded>

  <!-- WordPress固有要素 -->
  <wp:post_id>123</wp:post_id>
  <wp:post_date><![CDATA[2024-12-30 12:00:00]]></wp:post_date>
  <wp:post_date_gmt><![CDATA[2024-12-30 03:00:00]]></wp:post_date_gmt>
  <wp:comment_status><![CDATA[open]]></wp:comment_status>
  <wp:ping_status><![CDATA[open]]></wp:ping_status>
  <wp:post_name><![CDATA[post-slug]]></wp:post_name>
  <wp:status><![CDATA[publish]]></wp:status>
  <wp:post_parent>0</wp:post_parent>
  <wp:menu_order>0</wp:menu_order>
  <wp:post_type><![CDATA[post]]></wp:post_type>
  <wp:post_password><![CDATA[]]></wp:post_password>
  <wp:is_sticky>0</wp:is_sticky>

  <!-- カテゴリ・タグ -->
  <category domain="category" nicename="news"><![CDATA[ニュース]]></category>
  <category domain="post_tag" nicename="wordpress"><![CDATA[WordPress]]></category>

  <!-- カスタムフィールド -->
  <wp:postmeta>
    <wp:meta_key><![CDATA[_thumbnail_id]]></wp:meta_key>
    <wp:meta_value><![CDATA[456]]></wp:meta_value>
  </wp:postmeta>

  <!-- コメント -->
  <wp:comment>
    <wp:comment_id>789</wp:comment_id>
    <wp:comment_author><![CDATA[山田太郎]]></wp:comment_author>
    <wp:comment_author_email><![CDATA[yamada@example.com]]></wp:comment_author_email>
    <wp:comment_author_url></wp:comment_author_url>
    <wp:comment_author_IP><![CDATA[192.168.1.1]]></wp:comment_author_IP>
    <wp:comment_date><![CDATA[2024-12-30 13:00:00]]></wp:comment_date>
    <wp:comment_date_gmt><![CDATA[2024-12-30 04:00:00]]></wp:comment_date_gmt>
    <wp:comment_content><![CDATA[コメント本文]]></wp:comment_content>
    <wp:comment_approved><![CDATA[1]]></wp:comment_approved>
    <wp:comment_type><![CDATA[]]></wp:comment_type>
    <wp:comment_parent>0</wp:comment_parent>
    <wp:comment_user_id>0</wp:comment_user_id>
  </wp:comment>
</item>
```

### 1.8 メディア要素（attachment）

```xml
<item>
  <title>image.jpg</title>
  <link>https://example.com/image/</link>
  <wp:post_id>456</wp:post_id>
  <wp:post_type><![CDATA[attachment]]></wp:post_type>
  <wp:attachment_url><![CDATA[https://example.com/wp-content/uploads/2024/12/image.jpg]]></wp:attachment_url>
  <wp:postmeta>
    <wp:meta_key><![CDATA[_wp_attachment_image_alt]]></wp:meta_key>
    <wp:meta_value><![CDATA[代替テキスト]]></wp:meta_value>
  </wp:postmeta>
</item>
```

### 1.9 ステータス値

| 値 | 説明 | Focomyマッピング |
|----|------|-----------------|
| `publish` | 公開済み | published |
| `draft` | 下書き | draft |
| `pending` | レビュー待ち | pending |
| `private` | 非公開 | private |
| `future` | 予約投稿 | scheduled |
| `trash` | ゴミ箱 | archived |
| `inherit` | 親を継承（リビジョン） | - |

### 1.10 投稿タイプ（wp:post_type）

| 値 | 説明 |
|----|------|
| `post` | 投稿 |
| `page` | 固定ページ |
| `attachment` | メディア |
| `revision` | リビジョン |
| `nav_menu_item` | ナビゲーションメニュー項目 |
| `custom_css` | カスタムCSS |
| `customize_changeset` | カスタマイザー変更セット |
| `oembed_cache` | oEmbedキャッシュ |
| （任意） | カスタム投稿タイプ |

### 1.11 ナビゲーションメニュー

メニューは`wp:term`と`nav_menu_item`投稿タイプで構成される。

```xml
<!-- メニュー定義（term） -->
<wp:term>
  <wp:term_id>10</wp:term_id>
  <wp:term_taxonomy>nav_menu</wp:term_taxonomy>
  <wp:term_slug><![CDATA[main-menu]]></wp:term_slug>
  <wp:term_name><![CDATA[メインメニュー]]></wp:term_name>
</wp:term>

<!-- メニュー項目（item） -->
<item>
  <title>ホーム</title>
  <wp:post_type><![CDATA[nav_menu_item]]></wp:post_type>
  <wp:postmeta>
    <wp:meta_key><![CDATA[_menu_item_type]]></wp:meta_key>
    <wp:meta_value><![CDATA[custom]]></wp:meta_value>
  </wp:postmeta>
  <wp:postmeta>
    <wp:meta_key><![CDATA[_menu_item_url]]></wp:meta_key>
    <wp:meta_value><![CDATA[/]]></wp:meta_value>
  </wp:postmeta>
  <wp:postmeta>
    <wp:meta_key><![CDATA[_menu_item_menu_item_parent]]></wp:meta_key>
    <wp:meta_value><![CDATA[0]]></wp:meta_value>
  </wp:postmeta>
  <category domain="nav_menu" nicename="main-menu"><![CDATA[メインメニュー]]></category>
</item>
```

**メニュー項目のメタキー:**

| メタキー | 説明 |
|---------|------|
| `_menu_item_type` | custom/post_type/taxonomy |
| `_menu_item_object` | 対象オブジェクト（post/page/category等） |
| `_menu_item_object_id` | 対象オブジェクトID |
| `_menu_item_url` | カスタムURL |
| `_menu_item_menu_item_parent` | 親メニュー項目ID |
| `_menu_item_target` | リンクターゲット（_blank等） |
| `_menu_item_classes` | CSSクラス |

### 1.12 カスタム投稿タイプ

カスタム投稿タイプは`wp:post_type`で任意の値を持つ。

```xml
<item>
  <title>商品A</title>
  <wp:post_type><![CDATA[product]]></wp:post_type>
  <wp:status><![CDATA[publish]]></wp:status>
  <!-- 通常の投稿と同じ構造 -->
</item>
```

**検出方法:**
- `wp:post_type`が`post`/`page`/`attachment`/`revision`/`nav_menu_item`以外
- 対応するカスタムタクソノミーも存在する可能性

### 1.13 ACF（Advanced Custom Fields）

ACFフィールドは`wp:postmeta`に2つのキーペアで保存される。

```xml
<!-- フィールド値 -->
<wp:postmeta>
  <wp:meta_key><![CDATA[custom_field]]></wp:meta_key>
  <wp:meta_value><![CDATA[フィールドの値]]></wp:meta_value>
</wp:postmeta>
<!-- フィールド参照 -->
<wp:postmeta>
  <wp:meta_key><![CDATA[_custom_field]]></wp:meta_key>
  <wp:meta_value><![CDATA[field_abc123]]></wp:meta_value>
</wp:postmeta>
```

**ACFフィールドタイプ:**

| タイプ | 値の形式 |
|--------|---------|
| text/textarea | 文字列 |
| number | 数値 |
| email/url | 文字列 |
| image/file | 添付ファイルID |
| wysiwyg | HTML |
| select/radio/checkbox | 選択値 |
| true_false | "1" or "" |
| date_picker | Y-m-d形式 |
| repeater | シリアライズされた配列 |
| flexible_content | シリアライズされた配列 |
| relationship | シリアライズされたID配列 |

---

## 2. WordPress REST API

### 2.1 概要

- **ベースURL**: `/wp-json/wp/v2/`
- **バージョン**: v2（WordPress 4.7以降）
- **デフォルト**: 有効（WordPress 4.7+）

### 2.2 エンドポイント一覧

| リソース | エンドポイント | メソッド |
|---------|--------------|---------|
| 投稿 | `/wp/v2/posts` | GET, POST |
| 投稿（個別） | `/wp/v2/posts/{id}` | GET, POST, DELETE |
| 固定ページ | `/wp/v2/pages` | GET, POST |
| メディア | `/wp/v2/media` | GET, POST |
| カテゴリ | `/wp/v2/categories` | GET, POST |
| タグ | `/wp/v2/tags` | GET, POST |
| ユーザー | `/wp/v2/users` | GET, POST |
| コメント | `/wp/v2/comments` | GET, POST |
| タクソノミー | `/wp/v2/taxonomies` | GET |
| 投稿タイプ | `/wp/v2/types` | GET |
| 設定 | `/wp/v2/settings` | GET, POST |
| 検索 | `/wp/v2/search` | GET |

### 2.3 共通パラメータ

| パラメータ | 説明 | デフォルト |
|-----------|------|-----------|
| `page` | ページ番号 | 1 |
| `per_page` | 1ページあたり件数（最大100） | 10 |
| `offset` | オフセット | 0 |
| `order` | 並び順（asc/desc） | desc |
| `orderby` | ソート項目 | date |
| `context` | レスポンス形式（view/edit/embed） | view |
| `search` | 検索キーワード | - |

### 2.4 Posts スキーマ

```json
{
  "id": 123,
  "date": "2024-12-30T12:00:00",
  "date_gmt": "2024-12-30T03:00:00",
  "modified": "2024-12-30T12:00:00",
  "modified_gmt": "2024-12-30T03:00:00",
  "slug": "post-slug",
  "status": "publish",
  "type": "post",
  "link": "https://example.com/post-slug/",
  "title": { "rendered": "投稿タイトル" },
  "content": { "rendered": "<p>本文HTML</p>", "protected": false },
  "excerpt": { "rendered": "<p>抜粋</p>", "protected": false },
  "author": 1,
  "featured_media": 456,
  "comment_status": "open",
  "ping_status": "open",
  "sticky": false,
  "template": "",
  "format": "standard",
  "categories": [2, 3],
  "tags": [5, 6],
  "meta": {}
}
```

### 2.5 Media スキーマ

```json
{
  "id": 456,
  "date": "2024-12-30T12:00:00",
  "slug": "image",
  "status": "inherit",
  "type": "attachment",
  "link": "https://example.com/image/",
  "title": { "rendered": "image.jpg" },
  "author": 1,
  "alt_text": "代替テキスト",
  "caption": { "rendered": "キャプション" },
  "description": { "rendered": "説明" },
  "media_type": "image",
  "mime_type": "image/jpeg",
  "source_url": "https://example.com/wp-content/uploads/2024/12/image.jpg",
  "media_details": {
    "width": 1920,
    "height": 1080,
    "file": "2024/12/image.jpg",
    "sizes": {
      "thumbnail": { "width": 150, "height": 150, "source_url": "..." },
      "medium": { "width": 300, "height": 169, "source_url": "..." },
      "large": { "width": 1024, "height": 576, "source_url": "..." }
    }
  }
}
```

### 2.6 Categories スキーマ

```json
{
  "id": 2,
  "count": 10,
  "description": "カテゴリの説明",
  "link": "https://example.com/category/news/",
  "name": "ニュース",
  "slug": "news",
  "taxonomy": "category",
  "parent": 0,
  "meta": []
}
```

### 2.7 認証方式

| 方式 | 用途 |
|------|------|
| Cookie | ブラウザ内（管理画面） |
| Application Passwords | 外部アプリケーション（WordPress 5.6+） |
| JWT | トークンベース認証（プラグイン） |
| OAuth 1.0 | サードパーティ連携（プラグイン） |

### 2.8 レート制限

- **デフォルト**: なし
- **per_page上限**: 100件
- **推奨**: 1秒あたり10リクエスト以下

---

## 3. データマッピング

### 3.1 WXR → Focomy

| WordPress | Focomy | 注意点 |
|-----------|--------|--------|
| wp:post_id | wp_id | 参照用に保持 |
| title | title | - |
| wp:post_name | slug | - |
| content:encoded | content | HTML、サニタイズ必須 |
| excerpt:encoded | excerpt | - |
| wp:status | status | マッピング必須 |
| wp:post_type | type | post/page/attachment等 |
| pubDate | created_at | RFC-822 → ISO8601 |
| wp:post_date_gmt | created_at | 優先使用 |
| dc:creator | author | ユーザーIDに変換 |
| category[@domain="category"] | categories | 関連付け |
| category[@domain="post_tag"] | tags | 関連付け |
| wp:postmeta | meta | キー/値で保持 |
| wp:attachment_url | source_url | メディアのみ |
| wp:comment | comments | ネスト構造維持 |

### 3.2 REST API → Focomy

| WordPress | Focomy | 注意点 |
|-----------|--------|--------|
| id | wp_id | 参照用に保持 |
| title.rendered | title | HTMLエンコード済み |
| slug | slug | - |
| content.rendered | content | HTML |
| excerpt.rendered | excerpt | HTML |
| status | status | そのまま使用可 |
| type | type | - |
| date_gmt | created_at | ISO8601 |
| modified_gmt | updated_at | ISO8601 |
| author | author | ユーザーIDで別途取得 |
| categories | categories | IDリスト、別途取得 |
| tags | tags | IDリスト、別途取得 |
| featured_media | featured_image | メディアID |
| source_url | source_url | メディアのみ |
| alt_text | alt_text | メディアのみ |
| media_details | - | サイズ情報等 |

---

## 4. 重要なメタキー

### 4.1 WordPress標準

| メタキー | 説明 |
|---------|------|
| `_thumbnail_id` | アイキャッチ画像ID |
| `_wp_page_template` | ページテンプレート |
| `_wp_attachment_image_alt` | 画像代替テキスト |
| `_wp_attached_file` | 添付ファイルパス |
| `_wp_attachment_metadata` | 画像メタデータ（シリアライズ） |
| `_edit_lock` | 編集ロック |
| `_edit_last` | 最終編集者 |

### 4.2 Yoast SEO

| メタキー | 説明 |
|---------|------|
| `_yoast_wpseo_title` | SEOタイトル |
| `_yoast_wpseo_metadesc` | メタディスクリプション |
| `_yoast_wpseo_focuskw` | フォーカスキーワード |
| `_yoast_wpseo_canonical` | 正規URL |
| `_yoast_wpseo_opengraph-title` | OGPタイトル |
| `_yoast_wpseo_opengraph-description` | OGP説明 |
| `_yoast_wpseo_opengraph-image` | OGP画像 |
| `_yoast_wpseo_twitter-title` | Twitterタイトル |
| `_yoast_wpseo_twitter-description` | Twitter説明 |

### 4.3 All in One SEO

| メタキー | 説明 |
|---------|------|
| `_aioseo_title` | SEOタイトル |
| `_aioseo_description` | メタディスクリプション |
| `_aioseo_og_title` | OGPタイトル |
| `_aioseo_og_description` | OGP説明 |

### 4.4 ACF（Advanced Custom Fields）

| メタキー | 説明 |
|---------|------|
| `_field_name` | ACFフィールド名（実際の値） |
| `__field_name` | フィールドキー参照 |

---

## 5. URL構造

### 5.1 パーマリンク形式

| 形式 | URL例 |
|------|-------|
| 基本 | `/?p=123` |
| 日付と投稿名 | `/2024/12/30/post-name/` |
| 月と投稿名 | `/2024/12/post-name/` |
| 数字ベース | `/archives/123` |
| 投稿名 | `/post-name/` |
| カスタム | `/blog/%postname%/` |

### 5.2 特殊URL

| URL | 用途 |
|-----|------|
| `/wp-admin/` | 管理画面 |
| `/wp-login.php` | ログイン |
| `/wp-content/uploads/` | メディアファイル |
| `/feed/` | RSSフィード |
| `/sitemap.xml` | サイトマップ（プラグイン） |
| `/category/{slug}/` | カテゴリアーカイブ |
| `/tag/{slug}/` | タグアーカイブ |
| `/author/{slug}/` | 著者アーカイブ |
| `/{year}/{month}/` | 日付アーカイブ |

---

## 6. 参照元

- [WordPress Tools Export Screen](https://wordpress.org/documentation/article/tools-export-screen/)
- [WordPress REST API Handbook](https://developer.wordpress.org/rest-api/)
- [Posts Endpoint](https://developer.wordpress.org/rest-api/reference/posts/)
- [Media Endpoint](https://developer.wordpress.org/rest-api/reference/media/)
- [Categories Endpoint](https://developer.wordpress.org/rest-api/reference/categories/)
- [WXR Format Decoded](https://devtidbits.com/2011/03/16/the-wordpress-extended-rss-wxr-exportimport-xml-document-format-decoded-and-explained/)
- [WXR XML Schema (Unofficial)](https://github.com/pbiron/wxr)
- [WordPress Data Liberation Discussion](https://github.com/WordPress/data-liberation/discussions/56)

---

更新日: 2025-12-31
