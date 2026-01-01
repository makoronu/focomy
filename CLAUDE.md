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
| インポート修正 | `.claude/prompts/2_dev/1_import/_main.md` |
| 緊急 | `.claude/prompts/emergency.md` |

---

## 必須ルール

1. **セッション開始時**: CLAUDE.md → 該当プロンプト読め
2. **作業中**: 工程位置を明示（例: `現在: 3_deploy/fly.md`）
3. **遷移時**: 「次 → ○○.md」と読み上げてから移動
4. **勝手にデプロイ禁止**
5. **プロンプト先読み**: 実行前に完了条件を確認

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
| DB | PostgreSQL |
| ORM | SQLAlchemy |
| テンプレート | Jinja2 |
| フロント | HTMX |
| エディタ | Editor.js |
| CSS | Tailwind |

---

## セッション

| 項目 | 内容 |
|------|------|
| 作業中 | なし |
| 完了 | 001-090, Issue #35/#36/#37修正, プロトコル違反修正(ENUM削除/重複コード共通化) |
| 残り | P2: 例外ログ追加, HTTPステータス定数化 |
| 更新 | 2026-01-01 |

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

## リリース

| バージョン | 日付 | リンク |
|-----------|------|--------|
| v0.1.0 | 2025-12-28 | [PyPI](https://pypi.org/project/focomy/0.1.0/) / [Fly.io](https://focomy.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.2 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.2/) / [GitHub](https://github.com/makoronu/focomy/releases/tag/v0.1.2) |
| v0.1.3 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.3/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy/releases/tag/v0.1.3) |
| v0.1.4 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.4/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy/releases/tag/v0.1.4) |
| v0.1.5 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.5/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.6 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.6/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.7 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.7/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.8 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.8/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.9 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.9/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.10 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.10/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.12 | 2025-12-29 | [PyPI](https://pypi.org/project/focomy/0.1.12/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.13 | 2025-12-30 | [PyPI](https://pypi.org/project/focomy/0.1.13/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.15 | 2025-12-31 | [PyPI](https://pypi.org/project/focomy/0.1.15/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.16 | 2025-12-31 | [PyPI](https://pypi.org/project/focomy/0.1.16/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.17 | 2025-12-31 | [PyPI](https://pypi.org/project/focomy/0.1.17/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.18 | 2025-12-31 | [PyPI](https://pypi.org/project/focomy/0.1.18/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.19 | 2025-12-31 | [PyPI](https://pypi.org/project/focomy/0.1.19/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.20 | 2026-01-01 | [PyPI](https://pypi.org/project/focomy/0.1.20/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) |
| v0.1.36 | 2026-01-01 | [PyPI](https://pypi.org/project/focomy/0.1.36/) / [GitHub](https://github.com/makoronu/focomy) - **チャンネル/シリーズ/タグ アーキテクチャ** |

---

## 参照

- [README.md](README.md) ← **運用手順・CLIコマンド・環境変数**
- [設計書](focomy_specification.md)
- [ロードマップ](docs/ROADMAP.md)
