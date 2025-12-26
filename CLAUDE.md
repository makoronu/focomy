# Focomy

**世界一美しいCMS**

メタデータ駆動 / 重複コードゼロ / リレーション完璧 / 無駄なし

## 工程プロンプト（必ず読め）

| 作業 | ファイル |
|------|---------|
| ロードマップ | `.claude/prompts/0_roadmap/_main.md` |
| 開発 | `.claude/prompts/2_dev/_main.md` |
| 検証 | `.claude/prompts/1_audit/_main.md` |
| デプロイ | `.claude/prompts/3_deploy/_main.md` |
| 振り返り | `.claude/prompts/4_retrospective/_main.md` |
| デバッグ | `.claude/prompts/5_debug/_main.md` |
| 緊急 | `.claude/prompts/emergency.md` |

---

## 必須ルール

1. **セッション開始時**: CLAUDE.md → 該当プロンプト読め
2. **作業中**: 「現在: ○○.md」と工程位置を明示
3. **遷移前**: 「次の工程」を読み上げてから移動
4. **勝手にデプロイ禁止**

---

## 設計哲学

**3つの抽象で全て表現**

1. **Entity** - 全コンテンツは統一エンティティ
2. **Field** - メタデータ駆動フィールド定義
3. **Relation** - リレーションは第一級市民

---

## 技術スタック

| 項目 | 技術 |
|------|------|
| バックエンド | FastAPI |
| DB | SQLite + FTS5 |
| ORM | SQLAlchemy |
| テンプレート | Jinja2 |
| フロント | HTMX |
| エディタ | Editor.js |
| CSS | Tailwind |

---

## セッション

| 項目 | 内容 |
|------|------|
| 作業中 | 001 プロジェクト基盤構築 |
| 完了 | - |
| 残り | 002-012 |
| 更新 | 2025-12-26 |

---

## 美しさの指標

| 指標 | 目標 |
|------|------|
| コアテーブル | 7以下 |
| サービスクラス | 5以下 |
| APIエンドポイント | 15以下 |
| 重複コード | 0 |
| 新コンテンツタイプ追加 | YAML 1ファイル |

---

## 起動

```bash
cd ~/my_programing/focomy/core && uvicorn main:app --reload --port 8000
```

---

## 参照

- [設計書](focomy_specification.md)
- [ロードマップ](docs/ROADMAP.md)
