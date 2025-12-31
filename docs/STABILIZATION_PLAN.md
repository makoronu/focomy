# 機能安定化計画

## 概要

全機能を一度無効化し、フェーズごとに有効化・安定化を行う。

---

## Phase 1: コア（認証 + CRUD）

### 有効のまま維持するサービス

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | auth | services/auth.py | ログイン/ログアウト/セッション |
| 2 | entity | services/entity.py | Entity CRUD |
| 3 | field | services/field.py | フィールド定義読込 |
| 4 | relation | services/relation.py | リレーション管理 |
| 5 | rbac | services/rbac.py | 権限チェック |
| 6 | pagination | services/pagination.py | ページネーション |
| 7 | cache | services/cache.py | キャッシュ |
| 8 | sanitizer | services/sanitizer.py | XSSサニタイズ |
| 9 | logging | services/logging.py | ロギング |
| 10 | theme | services/theme.py | テーマ描画 |
| 11 | settings | services/settings.py | サイト設定 |
| 12 | seo | services/seo.py | 基本SEO |
| 13 | query_optimizer | services/query_optimizer.py | クエリ最適化 |
| 14 | config_priority | services/config_priority.py | 設定優先度 |
| 15 | migration_helpers | services/migration_helpers.py | マイグレーション |
| 16 | index | services/index.py | DBインデックス作成 |

### 有効のまま維持するAPI

| # | API | ファイル | 機能 |
|---|-----|----------|------|
| 1 | auth | api/auth.py | 認証API |
| 2 | entities | api/entities.py | Entity API |
| 3 | relations | api/relations.py | リレーションAPI |
| 4 | schema | api/schema.py | スキーマAPI |
| 5 | seo | api/seo.py | SEO API |

### 有効のまま維持するコンテンツタイプ

| # | タイプ | 用途 |
|---|--------|------|
| 1 | user | ユーザー |
| 2 | post | 投稿 |
| 3 | page | 固定ページ |
| 4 | category | カテゴリ |
| 5 | tag | タグ |
| 6 | site_setting | サイト設定 |
| 7 | audit_log | 監査ログ |

---

## Phase 2: メディア

### 有効化するサービス

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | media | services/media.py | アップロード/管理 |
| 2 | thumbnail | services/thumbnail.py | サムネイル生成 |
| 3 | storage | services/storage.py | ファイル保存 |
| 4 | assets | services/assets.py | アセット配信 |
| 5 | media_cleanup | services/media_cleanup.py | 不要ファイル削除 |

### 有効化するAPI

| # | API | ファイル | 機能 |
|---|-----|----------|------|
| 1 | media | api/media.py | メディアAPI |

### 有効化するコンテンツタイプ

| # | タイプ | 用途 |
|---|--------|------|
| 1 | media | メディア |

---

## Phase 3: ACF代替（カスタムフィールド）

### 有効化するサービス

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | formula | services/formula.py | 計算フィールド |

### 備考
- Editor.js の blocks フィールドは Phase 1 で対応済み
- repeater/flexible_content フィールドタイプの安定化

---

## Phase 4: 補助機能（優先度順）

### 4-1: メニュー・ウィジェット

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | menu | services/menu.py | メニュー管理 |
| 2 | widget | services/widget.py | ウィジェット |

### 4-2: コンテンツ管理強化

| # | サービス/API | ファイル | 機能 |
|---|--------------|----------|------|
| 1 | revision | services/revision.py | リビジョン |
| 2 | revisions | api/revisions.py | リビジョンAPI |
| 3 | preview | services/preview.py | プレビュー |
| 4 | workflow | services/workflow.py | ワークフロー |
| 5 | edit_lock | services/edit_lock.py | 編集ロック |
| 6 | bulk | services/bulk.py | 一括操作 |

### 4-3: 検索・リダイレクト

| # | サービス/API | ファイル | 機能 |
|---|--------------|----------|------|
| 1 | search | services/search.py | 全文検索 |
| 2 | search | api/search.py | 検索API |
| 3 | redirect | services/redirect.py | リダイレクト |
| 4 | routing | services/routing.py | カスタムルーティング |

### 4-4: 監査・監視

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | audit | services/audit.py | 監査ログ |
| 2 | sentry | services/sentry.py | エラー監視 |
| 3 | link_validator | services/link_validator.py | リンク検証 |

---

## Phase 5: 拡張機能（優先度順）

### 5-1: コメント

| # | サービス/API | ファイル | 機能 |
|---|--------------|----------|------|
| 1 | comment | services/comment.py | コメント管理 |
| 2 | spam_filter | services/spam_filter.py | スパム対策 |
| 3 | comments | api/comments.py | コメントAPI |

### 5-2: フォーム

| # | サービス/API | ファイル | 機能 |
|---|--------------|----------|------|
| 1 | forms | api/forms.py | フォームAPI |

### 5-3: API認証

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | api_auth | services/api_auth.py | JWT/APIキー |

### 5-4: 外部連携

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | oauth | services/oauth.py | OAuth連携 |
| 2 | mail | services/mail.py | メール送信 |
| 3 | invite | services/invite.py | 招待機能 |

### 5-5: スケジュール・エクスポート

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | schedule | services/schedule.py | スケジュール投稿 |
| 2 | export | services/export.py | エクスポート |
| 3 | cleanup | services/cleanup.py | クリーンアップ |

### 5-6: 多言語

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | i18n | services/i18n.py | 多言語対応 |

---

## Phase 6: プラグイン・テーマ拡張

| # | サービス | ファイル | 機能 |
|---|----------|----------|------|
| 1 | plugin_resolver | services/plugin_resolver.py | 依存解決 |
| 2 | plugin_sandbox | services/plugin_sandbox.py | サンドボックス |
| 3 | theme_inheritance | services/theme_inheritance.py | テーマ継承 |
| 4 | marketplace | services/marketplace.py | マーケット |
| 5 | marketplace_verify | services/marketplace_verify.py | 署名検証 |
| 6 | update | services/update.py | アップデート |
| 7 | deployment | services/deployment.py | デプロイ |

---

## Phase 7: WordPress Import

| # | モジュール | ファイル | 機能 |
|---|------------|----------|------|
| 1 | wxr_parser | wordpress_import/wxr_parser.py | WXR解析 |
| 2 | rest_client | wordpress_import/rest_client.py | REST API |
| 3 | import_service | wordpress_import/import_service.py | インポート本体 |
| 4 | importer | wordpress_import/importer.py | インポーター |
| 5 | preview | wordpress_import/preview.py | プレビュー |
| 6 | rollback | wordpress_import/rollback.py | ロールバック |
| 7 | analyzer | wordpress_import/analyzer.py | 分析 |
| 8 | diff_detector | wordpress_import/diff_detector.py | 差分検出 |
| 9 | dry_run | wordpress_import/dry_run.py | ドライラン |
| 10 | verification | wordpress_import/verification.py | 検証 |
| 11 | media | wordpress_import/media.py | メディア |
| 12 | acf | wordpress_import/acf.py | ACF変換 |
| 13 | redirects | wordpress_import/redirects.py | リダイレクト |
| 14 | link_fixer | wordpress_import/link_fixer.py | リンク修正 |
| 15 | content_sanitizer | wordpress_import/content_sanitizer.py | コンテンツ整形 |
| 16 | constants | wordpress_import/constants.py | 定数 |

---

## 無効化方法

### 方針
- コードは削除しない
- 機能フラグで無効化
- `config.yaml` で制御

### 実装

```yaml
# config.yaml
features:
  # Phase 1: 常に有効
  core: true

  # Phase 2: メディア
  media: false

  # Phase 3: ACF代替
  acf_alternative: false

  # Phase 4: 補助機能
  menu: false
  widget: false
  revision: false
  preview: false
  workflow: false
  search: false
  redirect: false
  audit: false

  # Phase 5: 拡張機能
  comment: false
  form: false
  api_auth: false
  oauth: false
  schedule: false
  export: false
  i18n: false

  # Phase 6: プラグイン
  plugin: false
  marketplace: false

  # Phase 7: WordPress Import
  wordpress_import: false
```

---

## 作業順序

### Step 0: 準備
1. [ ] 機能フラグシステム実装
2. [ ] config.yaml に features セクション追加
3. [ ] 各サービスに機能フラグチェック追加

### Step 1: Phase 1 安定化
1. [ ] auth サービステスト
2. [ ] entity サービステスト
3. [ ] field サービステスト
4. [ ] relation サービステスト
5. [ ] rbac サービステスト
6. [ ] 管理画面 CRUD テスト
7. [ ] ログイン/ログアウトテスト

### Step 2: Phase 2 有効化・安定化
1. [ ] media フラグ有効化
2. [ ] アップロードテスト
3. [ ] サムネイル生成テスト
4. [ ] メディアライブラリテスト

### Step 3: Phase 3 有効化・安定化
1. [ ] acf_alternative フラグ有効化
2. [ ] 計算フィールドテスト
3. [ ] blocks フィールドテスト

### Step 4-7: 順次有効化
- 各フェーズごとにフラグ有効化→テスト→バグ修正

---

## 完了条件

各フェーズの完了条件：
1. 全機能が正常動作
2. エラーログなし
3. Seleniumテスト通過
4. 本番環境で動作確認

---

## 備考

- 無効化した機能のAPIは404を返す
- 無効化した機能の管理画面メニューは非表示
- 機能フラグはホットリロード対応
