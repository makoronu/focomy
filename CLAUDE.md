# Focomy

**世界一美しいCMS**

メタデータ駆動 / 重複コードゼロ / リレーション完璧 / 無駄なし

## 工程プロンプト（必ず読め）

### 基本フロー
| 作業 | ファイル |
|------|---------|
| ロードマップ | `.claude/prompts/0_roadmap/_main.md` |
| 検証 | `.claude/prompts/1_audit/_main.md` |
| 開発 | `.claude/prompts/2_dev/_main.md` |
| デプロイ | `.claude/prompts/3_deploy/_main.md` |
| 振り返り | `.claude/prompts/4_retrospective/_main.md` |

### 運用・保守
| 作業 | ファイル |
|------|---------|
| デバッグ | `.claude/prompts/5_debug/_main.md` |
| 本番環境整備 | `.claude/prompts/5_production/_main.md` |
| エラーログ | `.claude/prompts/6_error_log/_main.md` |
| マニュアル生成 | `.claude/prompts/6_manual/_main.md` |

### サブ工程
| 作業 | ファイル |
|------|---------|
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

## パッケージアーキテクチャ

```
パッケージ（pip install）
├── core/
│   ├── content_types/   ← コア定義（単一情報源、上書き不可）
│   ├── relations.yaml   ← コアリレーション
│   └── ...

ユーザーサイト（focomy init）
├── plugins/             ← ユーザー拡張（追加のみ）
├── themes/
├── config.yaml
└── uploads/
```

**原則**: コア定義は常にパッケージから。ユーザーは追加のみ、上書き不可。

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
| 完了 | 001-092, Issue #128 S0-S3, コア/ユーザー層分離アーキテクチャ(v0.1.88) |
| 残り | Issue #128 S2.5-B/C/D/S4-S6 |
| 更新 | 2026-01-13 |

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
| v0.1.45 | 2026-01-02 | [PyPI](https://pypi.org/project/focomy/0.1.45/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **編集画面フィールド整理** |
| v0.1.57 | 2026-01-03 | [PyPI](https://pypi.org/project/focomy/0.1.57/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **エディタUX改善(128-S1-A4)** |
| v0.1.58 | 2026-01-03 | [PyPI](https://pypi.org/project/focomy/0.1.58/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **フォームレイアウト2カラム化(128-S2)** |
| v0.1.59 | 2026-01-03 | [PyPI](https://pypi.org/project/focomy/0.1.59/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **CSSライブ調整機能(128-S2.5-A)** |
| v0.1.62 | 2026-01-11 | [PyPI](https://pypi.org/project/focomy/0.1.62/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **メニュー・ウィジェット機能有効化** |
| v0.1.63 | 2026-01-11 | [PyPI](https://pypi.org/project/focomy/0.1.63/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **テーマ・メニュー デフォルト設定追加** |
| v0.1.65 | 2026-01-11 | [PyPI](https://pypi.org/project/focomy/0.1.65/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **テーマ設定読み込みバグ修正** |
| v0.1.68 | 2026-01-11 | [PyPI](https://pypi.org/project/focomy/0.1.68/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **管理バー機能(128-S3)** |
| v0.1.69 | 2026-01-11 | [PyPI](https://pypi.org/project/focomy/0.1.69/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **管理バーキャッシュバイパス修正** |
| v0.1.70 | 2026-01-11 | [PyPI](https://pypi.org/project/focomy/0.1.70/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **管理バー改善・テーマ読み込みロジック修正** |
| v0.1.71 | 2026-01-11 | [PyPI](https://pypi.org/project/focomy/0.1.71/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **Pathインポート修正(v0.1.70バグ修正)** |
| v0.1.72 | 2026-01-12 | [PyPI](https://pypi.org/project/focomy/0.1.72/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **管理画面に「サイトを表示」リンク追加** |
| v0.1.88 | 2026-01-13 | [PyPI](https://pypi.org/project/focomy/0.1.88/) / [Fly.io](https://focomy-cms.fly.dev) / [GitHub](https://github.com/makoronu/focomy) - **コア/ユーザー層分離アーキテクチャ** |

---

## 参照

- [README.md](README.md) ← **運用手順・CLIコマンド・環境変数**
- [設計書](focomy_specification.md)
- [ロードマップ](docs/ROADMAP.md)
