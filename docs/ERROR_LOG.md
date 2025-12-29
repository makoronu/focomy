# エラーログ

全てのエラー報告と対応を記録。

---

## [ERR-001] coroutine object has no attribute 'encode'

| 項目 | 内容 |
|------|------|
| 報告日 | 2025-12-29 |
| 報告者 | GitHub Issue #1 Comment |
| バージョン | v0.1.2 |
| ステータス | 完了 |
| 対応バージョン | v0.1.3 |

### 症状
```
AttributeError: 'coroutine' object has no attribute 'encode'
File "core/engine/routes.py", line 239
```

### 原因
`cache_service.get()` / `cache_service.set()` が async メソッドだが `await` なしで呼び出し

### 対応
- routes.py: 6箇所に `await` 追加
- entity.py: `_invalidate_cache` を async 化
- Commit: ac73612

---

## [ERR-002] TemplateNotFound: 'home.html'

| 項目 | 内容 |
|------|------|
| 報告日 | 2025-12-29 |
| 報告者 | GitHub Issue #1 Comment |
| バージョン | v0.1.3 |
| ステータス | 完了 |
| 対応バージョン | v0.1.4 |

### 症状
```
jinja2.exceptions.TemplateNotFound: 'home.html' not found in search path
```

### 原因
- theme.py が `index.html` を生成
- routes.py が `home.html` を期待
- テンプレート名の不一致

### 対応
- theme.py: `index.html` → `home.html` に修正
- 欠落テンプレート追加: category.html, archive.html, search.html, post.html
- scaffold にも同様のテンプレート追加
- Commit: b5b7a00

---

## [ERR-003] No filter named 'date'

| 項目 | 内容 |
|------|------|
| 報告日 | 2025-12-29 |
| 報告者 | GitHub Issue #1 Comment |
| バージョン | v0.1.4 |
| ステータス | 完了 |
| 対応バージョン | v0.1.5 |

### 症状
```
jinja2.exceptions.TemplateAssertionError: No filter named 'date'.
File "themes/default/templates/home.html", line 23
```

### 原因
Jinja2環境に `date` フィルターが登録されていない

### 対応
- theme.py: `_date_filter` メソッド追加
- ISO形式文字列、datetime、Noneに対応

---

## [ERR-004] Unknown content type: user

| 項目 | 内容 |
|------|------|
| 報告日 | 2025-12-29 |
| 報告者 | GitHub Issue #1 Comment |
| バージョン | v0.1.4 |
| ステータス | 完了 |
| 対応バージョン | v0.1.5 |

### 症状
```
$ focomy createuser -e admin@example.com -n Admin -r admin -p testpassword123
Error: Validation failed: [ValidationError(field='type', message='Unknown content type: user')]
```

### 原因
`user` コンテンツタイプが存在しない。ユーザー管理がEntityServiceを使用しているが、user.yaml が未定義。

### 対応
- scaffold/content_types/user.yaml を追加
- name, email, role, password フィールド定義

---

## [ERR-005] No 'script_location' key found

| 項目 | 内容 |
|------|------|
| 報告日 | 2025-12-29 |
| 報告者 | GitHub Issue #1 Comment |
| バージョン | v0.1.4 |
| ステータス | 完了 |
| 対応バージョン | v0.1.5 |

### 症状
```
$ focomy migrate
alembic.util.exc.CommandError: No 'script_location' key found in configuration.
```

### 原因
Alembic設定で `script_location` が指定されていない

### 対応
- cli.py: alembic.ini がない場合はプログラムで設定を生成
- migrations ディレクトリの存在確認も追加

---

## [ERR-006] 既存サイトにテンプレートがコピーされない

| 項目 | 内容 |
|------|------|
| 報告日 | 2025-12-29 |
| 報告者 | GitHub Issue #1 Comment |
| バージョン | v0.1.4 |
| ステータス | 保留 |
| 対応バージョン | - |

### 症状
`focomy update` は pip バージョンチェックのみで、テーマファイルの同期は行われない

### 原因
設計上、既存サイトのテーマ更新機能が存在しない

### 対応
（検討）`focomy update --sync-themes` オプション追加を検討

---

## [ERR-007] 'str' object has no attribute 'name'

| 項目 | 内容 |
|------|------|
| 報告日 | 2025-12-29 |
| 報告者 | GitHub Issue #1 Comment |
| バージョン | v0.1.5 |
| ステータス | 完了 |
| 対応バージョン | v0.1.6 |

### 症状
```
$ focomy validate
Validating content type definitions...
  Checking {ct.name}...
AttributeError: 'str' object has no attribute 'name'
```

### 原因
`get_all_content_types()` は `dict[str, ContentType]` を返すが、`for ct in content_types:` でキー（文字列）をイテレートしていた

### 対応
- cli.py: `for ct in content_types:` → `for ct in content_types.values():`
