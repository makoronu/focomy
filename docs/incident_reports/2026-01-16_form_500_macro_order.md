# インシデントレポート: フォーム表示500エラー

- **検証日**: 2026-01-16
- **対象**: themes/default/templates/form.html
- **プロトコル参照**: 17-3. バグ修正時チェック

---

## 1. 調査

### 発生事象
- 4690.tuishou.info/forms/contact で500エラー発生
- PM2エラーログ: `jinja2.exceptions.UndefinedError: 'render_field' is undefined`

### 構造分析
- form.html 内で `render_field` マクロを105行目・126行目で使用
- マクロ定義は137行目〜206行目に配置（使用箇所の後）
- Jinja2ではマクロは使用前に定義される必要がある

---

## 2. 分析

### Why（根本原因）
1. マクロ定義が使用箇所より後ろに配置されていた
2. Jinja2のマクロスコープは定義順に依存
3. テンプレート作成時に順序を誤った

### 重複チェック
- 過去の類似インシデント: なし

### メタデータ駆動観点
- 該当なし（テンプレート構文の問題）

---

## 3. 判定

### 決定
- `render_field`マクロを`{% extends %}`の直後（3行目）に移動
- 重複定義（137-206行目）を削除

### 解決種別
**根本解決**

### レポート
- 対象ファイル: themes/default/templates/form.html
- 変更行数: -70行（重複削除）
- 影響: フォーム表示機能が正常化

---

## 教訓

1. Jinja2テンプレートでマクロは使用前に定義する
2. テンプレート作成時は構造（extends → macro → block）の順序を確認

---

## 影響範囲

- 影響を受けたサイト: 4690.tuishou.info（推手協会）
- 影響機能: /forms/{slug} ページ
- 影響時間: 不明（v0.1.109デプロイ以降）

---

## 関連ドキュメント

- Jinja2 Template Designer Documentation
- Focomy Issue #128（フォーム機能）
