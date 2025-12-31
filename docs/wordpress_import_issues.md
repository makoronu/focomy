# WordPress Import 機能 - 問題点と修正計画

## 概要

WordPress Import機能の現状分析、問題点の特定、あるべきプロセス・スキーマ・バリデーションを明文化する。

## 関連ドキュメント

- `docs/wordpress_specification.md` ← **WordPress仕様（WXR/REST API）**
- `docs/wordpress_import_plan.md` ← 設計詳細

---

## 1. 現状のファイル構成

```
core/
├── models/
│   └── import_job.py          # ImportJobモデル
├── services/
│   └── wordpress_import/
│       ├── __init__.py
│       ├── import_service.py  # メインサービス
│       ├── wxr_parser.py      # WXRパーサー
│       ├── rest_client.py     # REST APIクライアント
│       ├── analyzer.py        # サイト分析
│       ├── media.py           # メディアインポート
│       ├── acf.py             # ACFフィールド
│       ├── redirects.py       # リダイレクト生成
│       └── importer.py        # コアインポーター
├── admin/
│   └── routes.py              # ルート定義（問題あり）
└── templates/
    └── admin/
        └── import.html        # UI
```

---

## 2. 問題点一覧

### 2.1 致命的バグ

| ID | 問題 | 影響 | 原因 |
|----|------|------|------|
| BUG-001 | `/admin/import`が404 | インポート画面にアクセス不可 | ルート順序問題 |
| BUG-002 | `/admin/system`が404 | システム情報画面にアクセス不可 | ルート順序問題 |

**詳細（BUG-001, BUG-002）:**
```
routes.py の定義順序:
  1671行: @router.get("/{type_name}")  ← 動的ルート（先）
  2204行: @router.get("/system")       ← 静的ルート（後）
  2234行: @router.get("/import")       ← 静的ルート（後）

FastAPIは定義順にマッチング → /system, /import が {type_name} にマッチ
→ type_name="system" or "import" として処理 → コンテンツタイプ存在せず → 404
```

### 2.2 設計上の問題

| ID | 問題 | 影響度 | 現状 |
|----|------|--------|------|
| DESIGN-001 | ドライラン機能なし | 高 | 未実装 |
| DESIGN-002 | プレビュー機能なし | 高 | 未実装 |
| DESIGN-003 | ロールバック機能なし | 高 | 未実装 |
| DESIGN-004 | チェックポイントなし | 中 | 途中再開不可 |
| DESIGN-005 | 差分インポートなし | 中 | 毎回フルインポート |
| DESIGN-006 | 内部リンク修正なし | 中 | リンク切れ発生 |
| DESIGN-007 | コンテンツサニタイズ不足 | 高 | XSS等のリスク |
| DESIGN-008 | SEO監査なし | 低 | 移行後の確認なし |

### 2.3 API設計の問題

| ID | 問題 | 現状 |
|----|------|------|
| API-001 | バリデーション不足 | `await request.json()` で直接取得、スキーマ検証なし |
| API-002 | エラーレスポンス非統一 | `{"success": False, "error": str(e)}` or `{"success": False, "message": ...}` |
| API-003 | HTTPステータスコード不適切 | エラー時も200返却 |
| API-004 | 認証バイパスリスク | `require_admin` 依存のみ |

### 2.4 計画書との乖離

`docs/wordpress_import_plan.md`（1800行超）と実装の差分:

| 計画書の機能 | 実装状況 |
|-------------|---------|
| WXRインポート | ✓ 実装済み |
| REST APIインポート | ✓ 実装済み |
| Direct DB接続 | ✗ 未実装 |
| サイト分析 | △ 一部実装 |
| ドライラン | ✗ 未実装 |
| プレビュー | ✗ 未実装 |
| 差分検出 | ✗ 未実装 |
| チェックポイント | ✗ 未実装 |
| 並列処理 | ✗ 未実装 |
| コンテンツサニタイズ | ✗ 未実装 |
| 内部リンク修正 | ✗ 未実装 |
| ACF完全対応 | △ 一部実装 |
| 多言語対応 | ✗ 未実装 |
| リダイレクト生成 | △ 一部実装 |
| SEO監査 | ✗ 未実装 |
| ロールバック | ✗ 未実装 |
| 通知連携 | ✗ 未実装 |
| 404監視 | ✗ 未実装 |

---

## 3. あるべきプロセス

### 3.1 インポートフロー

```
┌─────────────────────────────────────────────────────────────────┐
│                     WordPress Import フロー                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [1. ソース選択]                                                 │
│       │                                                          │
│       ├─── WXRファイル                                           │
│       ├─── REST API                                              │
│       └─── Direct DB（未実装）                                   │
│             │                                                    │
│             ▼                                                    │
│  [2. 分析] ← バリデーション                                      │
│       │                                                          │
│       ├─── サイト情報取得                                        │
│       ├─── コンテンツ統計                                        │
│       ├─── プラグイン検出                                        │
│       ├─── 警告・エラー検出                                      │
│       └─── 推定時間・容量算出                                    │
│             │                                                    │
│             ▼                                                    │
│  [3. オプション設定]                                             │
│       │                                                          │
│       ├─── インポート対象選択                                    │
│       ├─── メディア設定（ダウンロード・WebP変換）                │
│       ├─── コンフリクト解決方法                                  │
│       └─── リダイレクト設定                                      │
│             │                                                    │
│             ▼                                                    │
│  [4. ドライラン] ← 必須                                          │
│       │                                                          │
│       ├─── 全データをシミュレーション                            │
│       ├─── 重複検出                                              │
│       ├─── エラー事前検出                                        │
│       └─── 生成されるリダイレクト一覧                            │
│             │                                                    │
│             ▼                                                    │
│  [5. 確認・承認] ← ユーザー確認必須                              │
│       │                                                          │
│       ├─── ドライラン結果確認                                    │
│       ├─── 警告内容確認                                          │
│       └─── 最終承認                                              │
│             │                                                    │
│             ▼                                                    │
│  [6. 本番インポート]                                             │
│       │                                                          │
│       ├─── チェックポイント保存                                  │
│       ├─── 依存順にインポート                                    │
│       │     (Authors → Categories → Tags → Media →               │
│       │      Posts → Pages → Comments → Menus)                   │
│       ├─── 内部リンク修正                                        │
│       ├─── リダイレクト生成                                      │
│       └─── 進捗リアルタイム通知                                  │
│             │                                                    │
│             ▼                                                    │
│  [7. 検証]                                                       │
│       │                                                          │
│       ├─── 件数チェック                                          │
│       ├─── リレーション整合性                                    │
│       ├─── メディア参照チェック                                  │
│       ├─── 内部リンクチェック                                    │
│       └─── SEO監査                                               │
│             │                                                    │
│             ▼                                                    │
│  [8. 完了レポート]                                               │
│       │                                                          │
│       └─── ロールバック可能期間開始                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 状態遷移

```
PENDING → ANALYZING → ANALYZED → DRY_RUNNING → DRY_RUN_COMPLETE
                                                      │
                                                      ▼
CANCELLED ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  IMPORTING
                                                      │
                                                      ▼
                                              VALIDATING
                                                      │
                                                      ▼
                      ROLLED_BACK ← ─ ─ ─ ─  COMPLETED
```

---

## 4. APIスキーマ

### 4.1 リクエスト/レスポンス統一フォーマット

```python
# 成功時
{
    "success": True,
    "data": { ... },
    "meta": {
        "request_id": "uuid",
        "timestamp": "ISO8601"
    }
}

# エラー時
{
    "success": False,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Human readable message",
        "details": [ ... ],
        "request_id": "uuid"
    }
}
```

### 4.2 エンドポイント定義

#### POST /admin/import/analyze

```yaml
Request:
  Content-Type: multipart/form-data
  Body:
    source_type: enum["wxr", "rest_api"]  # required
    file: File  # required if source_type == "wxr"
    url: string  # required if source_type == "rest_api"
    username: string  # optional
    password: string  # optional

Response (200):
  success: true
  data:
    job_id: string
    analysis:
      site_url: string
      site_name: string
      wp_version: string
      posts:
        total: int
        published: int
        draft: int
      pages:
        total: int
        published: int
        draft: int
      media:
        total_count: int
        by_type: object
      categories_count: int
      tags_count: int
      warnings: array
      recommendations: array
      estimated_time: string
      estimated_storage: string

Response (400):
  success: false
  error:
    code: "VALIDATION_ERROR"
    message: "Invalid source_type"

Response (422):
  success: false
  error:
    code: "ANALYSIS_FAILED"
    message: "Failed to parse WXR file"
    details: [...]
```

#### POST /admin/import/{job_id}/dry-run

```yaml
Request:
  Content-Type: application/json
  Body:
    options:
      import_media: boolean
      download_media: boolean
      convert_to_webp: boolean
      webp_quality: int (1-100)
      include_drafts: boolean
      import_comments: boolean
      import_menus: boolean
      conflict_resolution: enum["skip", "overwrite", "rename"]

Response (200):
  success: true
  data:
    will_import:
      posts: int
      pages: int
      media: int
      categories: int
      tags: int
    conflicts: array
    warnings: array
    errors: array
    redirects_to_create: int
```

#### POST /admin/import/{job_id}/start

```yaml
Request:
  Content-Type: application/json
  Body:
    confirm: true  # 必須: ドライラン確認済みフラグ

Response (200):
  success: true
  data:
    job_id: string
    status: "importing"

Response (400):
  success: false
  error:
    code: "DRY_RUN_REQUIRED"
    message: "Dry run must be completed before import"
```

#### GET /admin/import/{job_id}/status

```yaml
Response (200):
  success: true
  data:
    id: string
    status: enum["pending", "analyzing", "dry_running", "importing", "validating", "completed", "failed", "cancelled"]
    phase: string
    progress:
      current: int
      total: int
      percent: int
      message: string
    results:
      posts: int
      pages: int
      media: int
      ...
    errors: array
    warnings: array
```

#### POST /admin/import/{job_id}/cancel

```yaml
Response (200):
  success: true
  data:
    status: "cancelled"

Response (400):
  success: false
  error:
    code: "CANNOT_CANCEL"
    message: "Job is already completed"
```

#### POST /admin/import/{job_id}/rollback

```yaml
Request:
  Content-Type: application/json
  Body:
    confirm: true
    reason: string  # optional

Response (200):
  success: true
  data:
    rolled_back:
      posts: int
      pages: int
      media: int
      ...

Response (400):
  success: false
  error:
    code: "ROLLBACK_EXPIRED"
    message: "Rollback window has expired (30 days)"
```

---

## 5. バリデーションルール

### 5.1 ソース検証

```python
class SourceValidator:
    """ソースデータのバリデーション"""

    rules = {
        "wxr_file": {
            "max_size": "100MB",
            "allowed_extensions": [".xml"],
            "required_elements": ["channel", "item"],
            "encoding": "UTF-8",
        },
        "rest_api": {
            "url_pattern": r"^https?://",
            "timeout": 30,
            "required_endpoints": ["/wp-json/wp/v2/posts"],
        }
    }
```

### 5.2 コンテンツ検証

```python
class ContentValidator:
    """コンテンツのバリデーション"""

    rules = {
        "title": {
            "max_length": 500,
            "required": True,
            "sanitize": ["strip", "escape_html"],
        },
        "slug": {
            "pattern": r"^[a-z0-9\-]+$",
            "max_length": 200,
            "unique": True,
        },
        "content": {
            "max_length": 10_000_000,  # 10MB
            "sanitize": ["dangerous_tags", "dangerous_attrs", "base64_check"],
        },
        "status": {
            "allowed": ["draft", "published", "pending", "private", "scheduled"],
        }
    }
```

### 5.3 セキュリティ検証

```python
class SecurityValidator:
    """セキュリティバリデーション"""

    # 除去対象タグ
    DANGEROUS_TAGS = ["script", "iframe", "object", "embed", "form", "base"]

    # 除去対象属性
    DANGEROUS_ATTRS = ["onclick", "onerror", "onload", "onmouseover", "onfocus"]

    # 検出対象パターン
    SUSPICIOUS_PATTERNS = [
        r"javascript:",
        r"data:text/html",
        r"vbscript:",
        r"<\s*script",
        r"eval\s*\(",
        r"expression\s*\(",
    ]
```

---

## 6. 修正計画

### 6.1 Phase 1: 致命的バグ修正（即時対応）

#### BUG-001, BUG-002: ルート順序修正

**修正内容:**
```
移動対象: routes.py 2182-2451行
  - # === Update Check === (2182行)
  - GET /api/update-check (2185行)
  - GET /system (2204行)
  - # === WordPress Import === (2231行)
  - GET /import (2234行)
  - POST /import/test-connection (2245行)
  - POST /import/analyze (2283行)
  - POST /import/{job_id}/start (2373行)
  - GET /import/{job_id}/status (2411行)
  - POST /import/{job_id}/cancel (2434行)

移動先: 1668行（# === Entity List === の直前）
```

**手順:**
1. routes.py をバックアップ
2. 2182-2451行のコードを切り取り
3. 1668行の前に貼り付け
4. 構文チェック
5. サーバー起動テスト
6. /admin/system と /admin/import にアクセス確認

### 6.2 Phase 2: API改善（次回リリース）

- [ ] バリデーションスキーマ追加（Pydantic）
- [ ] エラーレスポンス統一
- [ ] HTTPステータスコード修正
- [ ] リクエストID追加

### 6.3 Phase 3: 機能追加（計画）

- [ ] ドライラン機能
- [ ] プレビュー機能
- [ ] ロールバック機能
- [ ] チェックポイント
- [ ] コンテンツサニタイズ
- [ ] 内部リンク修正

---

## 7. テスト計画

### 7.1 ルート修正後のテスト

```bash
# 1. サーバー起動
cd ~/my_programing/focomy/core && uvicorn main:app --reload --port 8000

# 2. ルートアクセステスト
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/admin/system
# 期待値: 302 (ログインリダイレクト) or 200 (ログイン済み)

curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/admin/import
# 期待値: 302 (ログインリダイレクト) or 200 (ログイン済み)

# 3. 既存ルートが壊れていないことを確認
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/admin/post
# 期待値: 302 or 200

curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/admin/media
# 期待値: 302 or 200
```

---

## 8. リスクと対策

| リスク | 影響度 | 対策 |
|--------|--------|------|
| ルート移動で既存機能が壊れる | 高 | 移動前後でgit diff確認、テスト実行 |
| 大量データでメモリ不足 | 中 | バッチ処理、ストリーミング対応 |
| 外部サイトからのメディアダウンロード失敗 | 中 | リトライ、エラーログ、スキップオプション |
| XSS/悪意あるコンテンツ | 高 | コンテンツサニタイズ必須化 |
| インポート途中でサーバー停止 | 中 | チェックポイント導入 |

---

## 9. 付録

### 9.1 ImportJobモデル（現状）

```python
class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: str (UUID)
    source_type: str ("wxr" | "rest_api")
    source_url: str | None
    source_file: str | None
    status: str
    phase: str
    progress_current: int
    progress_total: int
    progress_message: str
    config: JSON
    analysis: JSON
    posts_imported: int
    pages_imported: int
    media_imported: int
    categories_imported: int
    tags_imported: int
    authors_imported: int
    menus_imported: int
    redirects_generated: int
    errors: JSON
    warnings: JSON
    created_at: datetime
    started_at: datetime
    completed_at: datetime
    created_by: str
```

### 9.2 関連Issue

- GitHub Issue #3: `/admin/import`が404を返す（ルート順序の問題）

---

更新日: 2025-12-31
作成者: Claude
