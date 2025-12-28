# コンテンツビルダー計画 v3（ACF完全代替・完全版）

## 概要
ACFのような柔軟性を持ちながら、データベースとしての整合性・堅牢性を備えたコンテンツタイプ管理システム。

---

## ACFの問題点と解決策

| 問題 | ACF | Focomy解決策 |
|------|-----|-------------|
| ストレージ | wp_postmeta（シリアライズ） | EAV + JSONB（クエリ可能） |
| 検索 | ほぼ不可能 | 全フィールド検索可能 |
| リレーション | ID参照のみ | 外部キー制約、参照整合性 |
| パフォーマンス | N+1問題 | プリロード、バッチ取得 |
| バリデーション | フロントのみ | サーバーサイド必須 |
| バージョン管理 | なし | フィールド定義の履歴管理 |
| マイグレーション | 手動 | 自動データ移行 |
| 条件付きロジック | 表示/非表示のみ | バリデーション、計算にも |
| 多言語 | プラグイン依存 | ネイティブ対応 |
| リビジョン | なし | エンティティごとの変更履歴 |
| ワークフロー | なし | 承認フロー対応 |

---

## 設計原則

1. **データ整合性**: 外部キー制約、ユニーク制約、NOT NULL
2. **検索可能**: すべてのフィールドがクエリ可能
3. **パフォーマンス**: 適切なインデックス、N+1回避、キャッシュ
4. **柔軟性**: UIでフィールド追加、コンテンツタイプ作成
5. **型安全**: 厳密なバリデーション、型変換
6. **追跡可能**: 変更履歴、監査ログ
7. **安全な変更**: マイグレーション、ロールバック
8. **セキュリティ**: 入力サニタイズ、フィールドレベル権限

---

## フィールドタイプ完全一覧

### 基本フィールド
| タイプ | 説明 | ストレージ | バリデーション | UIコンポーネント |
|--------|------|-----------|--------------|------------------|
| string | 短いテキスト | VARCHAR(255) | max_length, pattern, unique | input[type=text] |
| text | 長いテキスト | TEXT | max_length | textarea |
| number | 整数 | INTEGER | min, max, step | input[type=number] |
| float | 小数 | DECIMAL(10,4) | min, max, precision | input[type=number] |
| boolean | 真偽値 | BOOLEAN | - | checkbox / toggle |
| date | 日付 | DATE | min, max | date picker |
| datetime | 日時 | TIMESTAMP WITH TZ | min, max | datetime picker |
| time | 時刻 | TIME | - | time picker |
| email | メールアドレス | VARCHAR(255) | RFC 5322 | input[type=email] |
| url | URL | VARCHAR(2048) | URL形式 | input[type=url] |
| slug | スラッグ | VARCHAR(255) | 英数字-のみ | slug input |
| color | カラーコード | VARCHAR(9) | #RRGGBB(AA) | color picker |
| phone | 電話番号 | VARCHAR(20) | 国際形式対応 | tel input |
| money | 金額 | DECIMAL(15,4) | min, max, currency | money input |

### リッチコンテンツ
| タイプ | 説明 | ストレージ | 機能 |
|--------|------|-----------|------|
| blocks | ブロックエディタ | JSONB | Gutenberg風、カスタムブロック |
| markdown | Markdown | TEXT | プレビュー、シンタックス |
| wysiwyg | リッチテキスト | TEXT | TinyMCE/Quill |
| code | コード | TEXT | シンタックスハイライト、言語選択 |

### 選択フィールド
| タイプ | 説明 | ストレージ | UI |
|--------|------|-----------|-----|
| select | 単一選択 | VARCHAR | ドロップダウン |
| multiselect | 複数選択 | JSONB | マルチセレクト |
| radio | ラジオボタン | VARCHAR | ラジオボタン |
| checkbox | チェックボックス群 | JSONB | チェックボックス |
| button_group | ボタングループ | VARCHAR | ボタン選択 |

### メディアフィールド
| タイプ | 説明 | ストレージ | 機能 |
|--------|------|-----------|------|
| image | 画像 | UUID (FK) | プレビュー、リサイズ、focal point |
| file | ファイル | UUID (FK) | プレビュー、ダウンロード |
| gallery | 画像ギャラリー | JSONB | 複数画像、並び替え、キャプション |
| video | 動画 | VARCHAR/UUID | アップロード or oEmbed |
| audio | 音声 | UUID (FK) | 波形表示、再生 |
| svg | SVGアイコン | TEXT | インラインSVG、色変更 |

### リレーションフィールド
| タイプ | 説明 | ストレージ | 機能 |
|--------|------|-----------|------|
| relation | エンティティ参照 | UUID (FK) | 単一選択、検索、プレビュー |
| relations | 複数参照 | relations表 | 複数選択、並び替え、条件フィルタ |
| taxonomy | タクソノミー | relations表 | 階層表示、作成可能 |
| user | ユーザー参照 | UUID (FK) | ユーザー選択 |

### 構造フィールド（ACF Pro相当）
| タイプ | 説明 | ストレージ | 機能 |
|--------|------|-----------|------|
| repeater | 繰り返しフィールド | JSONB | 子フィールド、行操作、ドラッグ |
| flexible | フレキシブルコンテンツ | JSONB | レイアウト選択、並び替え |
| group | フィールドグループ | JSONB | 論理的グループ化、折りたたみ |
| clone | クローン | - | 他フィールドグループを参照 |

### 特殊フィールド
| タイプ | 説明 | ストレージ | 機能 |
|--------|------|-----------|------|
| map | 地図 | JSONB | 緯度経度、マーカー、Google Maps/Mapbox |
| address | 住所 | JSONB | 郵便番号自動補完、構造化 |
| link | リンク | JSONB | URL + タイトル + target |
| oembed | 埋め込み | VARCHAR | YouTube, Twitter等 |
| range | レンジスライダー | INTEGER/FLOAT | min, max, step |
| password | パスワード | VARCHAR(255) | ハッシュ化、強度表示 |
| hidden | 隠しフィールド | VARCHAR | 自動生成値、システム用 |
| calculated | 計算フィールド | - | 他フィールドから自動計算（読み取り専用） |
| lookup | ルックアップ | - | リレーション先の値を参照（読み取り専用） |

---

## 高度な機能

### 1. 条件付きロジック（Conditional Logic）

```yaml
# フィールド定義
fields:
  - name: product_type
    type: select
    options:
      - value: physical
        label: 物理商品
      - value: digital
        label: デジタル商品
      - value: service
        label: サービス

  - name: weight
    type: float
    label: 重量 (kg)
    # 物理商品の場合のみ表示・必須
    conditions:
      show:
        - field: product_type
          operator: equals
          value: physical
      required:
        - field: product_type
          operator: equals
          value: physical

  - name: download_url
    type: url
    label: ダウンロードURL
    conditions:
      show:
        - field: product_type
          operator: equals
          value: digital
      required:
        - field: product_type
          operator: equals
          value: digital

  - name: duration
    type: number
    label: 所要時間 (分)
    conditions:
      show:
        - field: product_type
          operator: equals
          value: service
```

#### 条件演算子
```python
OPERATORS = {
    'equals': lambda a, b: a == b,
    'not_equals': lambda a, b: a != b,
    'contains': lambda a, b: b in a,
    'not_contains': lambda a, b: b not in a,
    'starts_with': lambda a, b: str(a).startswith(str(b)),
    'ends_with': lambda a, b: str(a).endswith(str(b)),
    'greater_than': lambda a, b: float(a) > float(b),
    'less_than': lambda a, b: float(a) < float(b),
    'greater_equal': lambda a, b: float(a) >= float(b),
    'less_equal': lambda a, b: float(a) <= float(b),
    'is_empty': lambda a, _: not a,
    'is_not_empty': lambda a, _: bool(a),
    'matches': lambda a, b: re.match(b, str(a)),
    'in': lambda a, b: a in b,
    'not_in': lambda a, b: a not in b,
}
```

### 2. 計算フィールド（Calculated Fields）

```yaml
fields:
  - name: unit_price
    type: money
    label: 単価

  - name: quantity
    type: number
    label: 数量

  - name: tax_rate
    type: float
    label: 税率 (%)
    default: 10

  - name: subtotal
    type: calculated
    label: 小計
    formula: "unit_price * quantity"
    format: currency

  - name: tax_amount
    type: calculated
    label: 税額
    formula: "subtotal * (tax_rate / 100)"
    format: currency

  - name: total
    type: calculated
    label: 合計
    formula: "subtotal + tax_amount"
    format: currency
```

#### 計算エンジン
```python
class FormulaEngine:
    """安全な数式評価エンジン"""

    ALLOWED_FUNCTIONS = {
        'round': round,
        'floor': math.floor,
        'ceil': math.ceil,
        'abs': abs,
        'min': min,
        'max': max,
        'sum': sum,
        'avg': lambda *args: sum(args) / len(args),
        'if': lambda cond, t, f: t if cond else f,
        'concat': lambda *args: ''.join(str(a) for a in args),
        'len': len,
        'now': datetime.utcnow,
        'today': date.today,
        'year': lambda d: d.year,
        'month': lambda d: d.month,
        'day': lambda d: d.day,
    }

    def evaluate(self, formula: str, context: dict) -> Any:
        """数式を評価"""
        # 危険な式を拒否
        if any(kw in formula for kw in ['import', 'exec', 'eval', '__']):
            raise ValueError("Unsafe formula")

        # 変数を置換
        for name, value in context.items():
            formula = formula.replace(name, repr(value))

        # 安全な評価
        return eval(formula, {"__builtins__": {}}, self.ALLOWED_FUNCTIONS)
```

### 3. ルックアップフィールド（Lookup Fields）

```yaml
fields:
  - name: author
    type: relation
    target: user
    label: 著者

  - name: author_name
    type: lookup
    label: 著者名
    source: author
    field: display_name

  - name: author_email
    type: lookup
    label: 著者メール
    source: author
    field: email

  - name: category
    type: relation
    target: category
    label: カテゴリ

  - name: category_slug
    type: lookup
    source: category
    field: slug
```

### 4. バリデーションルール

```yaml
fields:
  - name: sku
    type: string
    label: SKU
    validation:
      - rule: unique
        scope: global  # または content_type
        message: "このSKUは既に使用されています"
      - rule: pattern
        value: "^[A-Z]{3}-[0-9]{6}$"
        message: "SKUはABC-123456の形式で入力してください"

  - name: start_date
    type: date
    label: 開始日

  - name: end_date
    type: date
    label: 終了日
    validation:
      - rule: after
        field: start_date
        message: "終了日は開始日より後の日付を選択してください"

  - name: email
    type: email
    validation:
      - rule: dns_check  # MXレコード確認
        message: "有効なメールドメインを入力してください"

  - name: website
    type: url
    validation:
      - rule: reachable  # URL到達確認（非同期）
        message: "URLにアクセスできません"
```

#### バリデーションルール一覧
```python
VALIDATION_RULES = {
    # 文字列
    'required': RequiredValidator,
    'min_length': MinLengthValidator,
    'max_length': MaxLengthValidator,
    'pattern': PatternValidator,
    'email': EmailValidator,
    'url': URLValidator,
    'slug': SlugValidator,

    # 数値
    'min': MinValidator,
    'max': MaxValidator,
    'between': BetweenValidator,
    'integer': IntegerValidator,
    'positive': PositiveValidator,
    'negative': NegativeValidator,

    # 日付
    'before': BeforeValidator,
    'after': AfterValidator,
    'between_dates': BetweenDatesValidator,
    'weekday': WeekdayValidator,
    'business_day': BusinessDayValidator,

    # リレーション
    'exists': ExistsValidator,
    'unique': UniqueValidator,
    'unique_combination': UniqueCombinationValidator,

    # カスタム
    'custom': CustomValidator,  # カスタム関数
    'async': AsyncValidator,    # 非同期バリデーション
}
```

### 5. フィールドのプリセット

```yaml
# presets/seo_fields.yaml
name: seo_fields
label: SEOフィールド
fields:
  - name: meta_title
    type: string
    label: メタタイトル
    max_length: 60
    placeholder: "ページタイトル | サイト名"

  - name: meta_description
    type: text
    label: メタ説明
    max_length: 160

  - name: og_image
    type: image
    label: OG画像
    instructions: "推奨サイズ: 1200x630px"

  - name: robots
    type: multiselect
    label: ロボット指示
    options:
      - value: noindex
        label: noindex
      - value: nofollow
        label: nofollow
      - value: noarchive
        label: noarchive

# 使用例
# content_types/post.yaml
name: post
label: 投稿
fields:
  - name: title
    type: string
    required: true
  # ... 他のフィールド

# プリセットを適用
presets:
  - seo_fields
```

### 6. 業種別スターターキット

```yaml
# starter_kits/ecommerce.yaml
name: ecommerce
label: ECサイト
description: オンラインショップに必要なコンテンツタイプ一式

content_types:
  - name: product
    label: 商品
    fields:
      - name: name
        type: string
        required: true
      - name: sku
        type: string
        unique: true
      - name: price
        type: money
        required: true
      - name: sale_price
        type: money
      - name: stock
        type: number
        default: 0
      - name: images
        type: gallery
      - name: description
        type: blocks
      - name: specifications
        type: repeater
        fields:
          - name: key
            type: string
          - name: value
            type: string

  - name: product_category
    label: 商品カテゴリ
    hierarchical: true

  - name: product_tag
    label: 商品タグ

  - name: order
    label: 注文
    admin_menu: true
    fields:
      - name: order_number
        type: string
        unique: true
      - name: status
        type: select
        options: [pending, processing, shipped, delivered, cancelled]
      - name: customer
        type: relation
        target: user
      - name: items
        type: repeater
        fields:
          - name: product
            type: relation
            target: product
          - name: quantity
            type: number
          - name: price
            type: money

# starter_kits/blog.yaml
name: blog
label: ブログ
description: ブログサイトに必要なコンテンツタイプ一式

content_types:
  - name: post
    label: 投稿
    # ...

  - name: category
    label: カテゴリ
    hierarchical: true

  - name: tag
    label: タグ

  - name: author
    label: 著者
    # ...

# starter_kits/corporate.yaml
name: corporate
label: コーポレートサイト
# ...
```

---

## リビジョン履歴（エンティティバージョン管理）

### リビジョンシステム

```python
class RevisionManager:
    """エンティティのリビジョン管理"""

    async def create_revision(
        self,
        entity: Entity,
        user_id: str,
        change_summary: str = None,
    ) -> Revision:
        """リビジョンを作成"""

        # 現在のデータをスナップショット
        data = self.entity_svc.serialize(entity)

        revision = Revision(
            entity_id=entity.id,
            content_type=entity.content_type,
            version=await self._get_next_version(entity.id),
            data=data,
            created_at=datetime.utcnow(),
            created_by=user_id,
            change_summary=change_summary,
        )

        await self.db.execute(insert(revisions).values(**asdict(revision)))
        await self.db.commit()

        return revision

    async def get_revisions(
        self,
        entity_id: str,
        limit: int = 50,
    ) -> list[Revision]:
        """リビジョン一覧を取得"""

        result = await self.db.execute(
            select(Revision)
            .where(Revision.entity_id == entity_id)
            .order_by(Revision.version.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def restore_revision(
        self,
        entity_id: str,
        version: int,
        user_id: str,
    ) -> Entity:
        """指定バージョンに復元"""

        revision = await self.get_revision(entity_id, version)
        if not revision:
            raise ValueError(f"Revision {version} not found")

        entity = await self.entity_svc.get(entity_id)

        # 現在の状態を新しいリビジョンとして保存
        await self.create_revision(
            entity,
            user_id,
            f"Restored from version {version}",
        )

        # リビジョンのデータで上書き
        await self.entity_svc.update(entity_id, revision.data)

        return await self.entity_svc.get(entity_id)

    async def compare_revisions(
        self,
        entity_id: str,
        version_a: int,
        version_b: int,
    ) -> RevisionDiff:
        """2つのリビジョンを比較"""

        rev_a = await self.get_revision(entity_id, version_a)
        rev_b = await self.get_revision(entity_id, version_b)

        return self._diff(rev_a.data, rev_b.data)
```

### リビジョンUI

```
┌──────────────────────────────────────────────────────────────────────┐
│  リビジョン履歴: 商品「プレミアムTシャツ」                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────┬────────────────────┬─────────────┬────────────────────────┐ │
│  │ Ver │ 日時               │ 編集者      │ 変更内容               │ │
│  ├─────┼────────────────────┼─────────────┼────────────────────────┤ │
│  │ 5   │ 2024-01-20 15:30  │ 田中太郎    │ 価格を更新             │ │
│  │ 4   │ 2024-01-18 10:15  │ 山田花子    │ 説明文を修正           │ │
│  │ 3   │ 2024-01-15 09:00  │ 田中太郎    │ 在庫数を更新           │ │
│  │ 2   │ 2024-01-10 14:20  │ 田中太郎    │ 画像を追加             │ │
│  │ 1   │ 2024-01-05 11:00  │ 山田花子    │ 初期作成               │ │
│  └─────┴────────────────────┴─────────────┴────────────────────────┘ │
│                                                                       │
│  [比較: Ver 5 と Ver 4]                                               │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ price:                                                          │ │
│  │   - 2980                                                        │ │
│  │   + 3480                                                        │ │
│  │                                                                  │ │
│  │ sale_price:                                                     │ │
│  │   - null                                                        │ │
│  │   + 2980                                                        │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  [閉じる]                               [Ver 4 に復元]               │
└──────────────────────────────────────────────────────────────────────┘
```

---

## ワークフロー（承認フロー）

### ワークフロー定義

```yaml
# workflows/content_review.yaml
name: content_review
label: コンテンツレビュー
description: 投稿の承認フロー

states:
  - name: draft
    label: 下書き
    initial: true
    color: gray

  - name: pending_review
    label: レビュー待ち
    color: yellow

  - name: in_review
    label: レビュー中
    color: blue

  - name: approved
    label: 承認済み
    color: green

  - name: rejected
    label: 却下
    color: red

  - name: published
    label: 公開中
    final: true
    color: green

transitions:
  - from: draft
    to: pending_review
    label: レビュー依頼
    permissions: [author, editor]

  - from: pending_review
    to: in_review
    label: レビュー開始
    permissions: [editor, admin]

  - from: in_review
    to: approved
    label: 承認
    permissions: [editor, admin]
    actions:
      - type: notify
        to: author
        message: "投稿が承認されました"

  - from: in_review
    to: rejected
    label: 却下
    permissions: [editor, admin]
    require_comment: true
    actions:
      - type: notify
        to: author
        message: "投稿が却下されました: {comment}"

  - from: rejected
    to: draft
    label: 修正
    permissions: [author]

  - from: approved
    to: published
    label: 公開
    permissions: [editor, admin]
    actions:
      - type: set_field
        field: published_at
        value: now

  - from: published
    to: draft
    label: 非公開に戻す
    permissions: [admin]
```

### ワークフローサービス

```python
class WorkflowService:
    """ワークフロー管理"""

    async def transition(
        self,
        entity: Entity,
        to_state: str,
        user_id: str,
        comment: str = None,
    ) -> Entity:
        """状態遷移を実行"""

        workflow = await self._get_workflow(entity.content_type)
        current_state = entity.get('workflow_state', workflow.initial_state)

        # 遷移可能かチェック
        transition = workflow.get_transition(current_state, to_state)
        if not transition:
            raise ValueError(f"Cannot transition from {current_state} to {to_state}")

        # 権限チェック
        user = await self.user_svc.get(user_id)
        if not self._has_permission(user, transition.permissions):
            raise PermissionError("You don't have permission for this transition")

        # コメント必須チェック
        if transition.require_comment and not comment:
            raise ValueError("Comment is required for this transition")

        # 遷移を実行
        await self.entity_svc.update(entity.id, {'workflow_state': to_state})

        # 履歴を記録
        await self._record_transition(entity.id, current_state, to_state, user_id, comment)

        # アクションを実行
        for action in transition.actions:
            await self._execute_action(action, entity, user_id, comment)

        return await self.entity_svc.get(entity.id)

    async def get_available_transitions(
        self,
        entity: Entity,
        user_id: str,
    ) -> list[Transition]:
        """利用可能な遷移を取得"""

        workflow = await self._get_workflow(entity.content_type)
        current_state = entity.get('workflow_state', workflow.initial_state)
        user = await self.user_svc.get(user_id)

        available = []
        for transition in workflow.transitions:
            if transition.from_state == current_state:
                if self._has_permission(user, transition.permissions):
                    available.append(transition)

        return available
```

---

## スケジュール公開・非公開

### スケジュール管理

```python
class ScheduleService:
    """スケジュール公開・非公開"""

    async def schedule_publish(
        self,
        entity_id: str,
        publish_at: datetime,
        user_id: str,
    ) -> ScheduledAction:
        """公開をスケジュール"""

        action = ScheduledAction(
            entity_id=entity_id,
            action_type='publish',
            scheduled_at=publish_at,
            created_by=user_id,
            status='pending',
        )

        await self.db.execute(insert(scheduled_actions).values(**asdict(action)))
        await self.db.commit()

        # バックグラウンドジョブをスケジュール
        await self.scheduler.add_job(
            self._execute_publish,
            'date',
            run_date=publish_at,
            args=[entity_id],
            id=f"publish_{entity_id}_{publish_at.isoformat()}",
        )

        return action

    async def schedule_unpublish(
        self,
        entity_id: str,
        unpublish_at: datetime,
        user_id: str,
        action: str = 'archive',  # archive, draft, delete
    ) -> ScheduledAction:
        """非公開をスケジュール"""

        action_record = ScheduledAction(
            entity_id=entity_id,
            action_type=f'unpublish_{action}',
            scheduled_at=unpublish_at,
            created_by=user_id,
            status='pending',
        )

        await self.db.execute(insert(scheduled_actions).values(**asdict(action_record)))
        await self.db.commit()

        await self.scheduler.add_job(
            self._execute_unpublish,
            'date',
            run_date=unpublish_at,
            args=[entity_id, action],
            id=f"unpublish_{entity_id}_{unpublish_at.isoformat()}",
        )

        return action_record

    async def cancel_scheduled(self, entity_id: str, action_type: str) -> None:
        """スケジュールをキャンセル"""

        await self.db.execute(
            update(scheduled_actions)
            .where(
                scheduled_actions.c.entity_id == entity_id,
                scheduled_actions.c.action_type == action_type,
                scheduled_actions.c.status == 'pending',
            )
            .values(status='cancelled')
        )
        await self.db.commit()

        # ジョブを削除
        try:
            self.scheduler.remove_job(f"{action_type}_{entity_id}")
        except:
            pass
```

---

## フィールドレベル権限

### 権限定義

```yaml
# content_types/order.yaml
name: order
label: 注文

fields:
  - name: order_number
    type: string
    permissions:
      read: [customer, staff, admin]
      write: []  # 自動生成、誰も書けない

  - name: status
    type: select
    permissions:
      read: [customer, staff, admin]
      write: [staff, admin]  # 顧客は変更不可

  - name: customer_notes
    type: text
    permissions:
      read: [customer, staff, admin]
      write: [customer]  # 顧客のみ書ける

  - name: internal_notes
    type: text
    permissions:
      read: [staff, admin]  # 顧客は見えない
      write: [staff, admin]

  - name: profit_margin
    type: float
    permissions:
      read: [admin]  # 管理者のみ
      write: [admin]
```

### 権限チェック

```python
class FieldPermissionService:
    """フィールドレベル権限"""

    async def filter_readable_fields(
        self,
        entity: Entity,
        user: User,
    ) -> dict:
        """読み取り可能なフィールドのみ返す"""

        content_type = await self.get_content_type(entity.content_type)
        data = self.entity_svc.serialize(entity)
        user_roles = await self.get_user_roles(user)

        filtered = {}
        for field in content_type.fields:
            read_permissions = field.get('permissions', {}).get('read', ['*'])

            if '*' in read_permissions or any(r in read_permissions for r in user_roles):
                filtered[field['name']] = data.get(field['name'])

        return filtered

    async def validate_writable_fields(
        self,
        content_type: str,
        data: dict,
        user: User,
    ) -> tuple[dict, list[str]]:
        """書き込み可能なフィールドのみ許可"""

        ct = await self.get_content_type(content_type)
        user_roles = await self.get_user_roles(user)

        allowed = {}
        denied = []

        for field_name, value in data.items():
            field = ct.get_field(field_name)
            if not field:
                continue

            write_permissions = field.get('permissions', {}).get('write', ['*'])

            if '*' in write_permissions or any(r in write_permissions for r in user_roles):
                allowed[field_name] = value
            else:
                denied.append(field_name)

        return allowed, denied
```

---

## 監査ログ

### 監査ログシステム

```python
class AuditLogService:
    """監査ログ"""

    async def log_change(
        self,
        entity: Entity,
        action: str,  # create, update, delete
        user_id: str,
        before_data: dict = None,
        after_data: dict = None,
        ip_address: str = None,
    ) -> AuditLog:
        """変更をログに記録"""

        # 差分を計算
        changes = None
        if before_data and after_data:
            changes = self._calculate_diff(before_data, after_data)

        log = AuditLog(
            entity_id=entity.id,
            content_type=entity.content_type,
            action=action,
            user_id=user_id,
            before_data=before_data,
            after_data=after_data,
            changes=changes,
            ip_address=ip_address,
            created_at=datetime.utcnow(),
        )

        await self.db.execute(insert(audit_logs).values(**asdict(log)))
        await self.db.commit()

        return log

    async def get_entity_history(
        self,
        entity_id: str,
        limit: int = 100,
    ) -> list[AuditLog]:
        """エンティティの変更履歴を取得"""

        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_user_activity(
        self,
        user_id: str,
        since: datetime = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """ユーザーの活動履歴を取得"""

        query = select(AuditLog).where(AuditLog.user_id == user_id)

        if since:
            query = query.where(AuditLog.created_at >= since)

        query = query.order_by(AuditLog.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    def _calculate_diff(self, before: dict, after: dict) -> list[dict]:
        """差分を計算"""
        changes = []

        all_keys = set(before.keys()) | set(after.keys())

        for key in all_keys:
            before_val = before.get(key)
            after_val = after.get(key)

            if before_val != after_val:
                changes.append({
                    'field': key,
                    'before': before_val,
                    'after': after_val,
                })

        return changes
```

---

## 編集ロック（同時編集防止）

### 編集ロックシステム

```python
class EditLockService:
    """編集ロック管理"""

    LOCK_TIMEOUT = 300  # 5分

    async def acquire_lock(
        self,
        entity_id: str,
        user_id: str,
    ) -> EditLock | None:
        """ロックを取得"""

        # 既存のロックをチェック
        existing = await self._get_lock(entity_id)

        if existing:
            # タイムアウトしていれば解放
            if existing.expires_at < datetime.utcnow():
                await self.release_lock(entity_id, existing.user_id)
            elif existing.user_id != user_id:
                # 他のユーザーがロック中
                return None

        # ロックを作成/更新
        lock = EditLock(
            entity_id=entity_id,
            user_id=user_id,
            acquired_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=self.LOCK_TIMEOUT),
        )

        await self.db.execute(
            insert(edit_locks)
            .values(**asdict(lock))
            .on_conflict_do_update(
                index_elements=['entity_id'],
                set_={
                    'user_id': user_id,
                    'acquired_at': lock.acquired_at,
                    'expires_at': lock.expires_at,
                }
            )
        )
        await self.db.commit()

        return lock

    async def release_lock(self, entity_id: str, user_id: str) -> bool:
        """ロックを解放"""

        result = await self.db.execute(
            delete(edit_locks)
            .where(
                edit_locks.c.entity_id == entity_id,
                edit_locks.c.user_id == user_id,
            )
        )
        await self.db.commit()

        return result.rowcount > 0

    async def refresh_lock(self, entity_id: str, user_id: str) -> bool:
        """ロックを延長"""

        result = await self.db.execute(
            update(edit_locks)
            .where(
                edit_locks.c.entity_id == entity_id,
                edit_locks.c.user_id == user_id,
            )
            .values(expires_at=datetime.utcnow() + timedelta(seconds=self.LOCK_TIMEOUT))
        )
        await self.db.commit()

        return result.rowcount > 0

    async def get_lock_info(self, entity_id: str) -> EditLock | None:
        """ロック情報を取得"""

        lock = await self._get_lock(entity_id)

        if lock and lock.expires_at < datetime.utcnow():
            await self.release_lock(entity_id, lock.user_id)
            return None

        return lock
```

---

## コンテンツタイプビルダーUI

### メイン画面

```
┌──────────────────────────────────────────────────────────────────────┐
│  コンテンツタイプ                                        [+ 新規作成] │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                                                                  │ │
│  │  📝 投稿 (post)                                          [編集] │ │
│  │     12フィールド | 523エントリ | 最終更新: 2024-01-15           │ │
│  │                                                                  │ │
│  ├──────────────────────────────────────────────────────────────────┤ │
│  │                                                                  │ │
│  │  📄 固定ページ (page)                                    [編集] │ │
│  │     8フィールド | 42エントリ | 最終更新: 2024-01-10             │ │
│  │                                                                  │ │
│  ├──────────────────────────────────────────────────────────────────┤ │
│  │                                                                  │ │
│  │  📦 商品 (product)                                       [編集] │ │
│  │     25フィールド | 156エントリ | 最終更新: 2024-01-20           │ │
│  │                                                                  │ │
│  ├──────────────────────────────────────────────────────────────────┤ │
│  │                                                                  │ │
│  │  🏷️ カテゴリ (category)                                 [編集] │ │
│  │     5フィールド | 28エントリ | システム                         │ │
│  │                                                                  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  スターターキット                                                    │
│  ┌────────────────┬────────────────┬────────────────┐               │
│  │ [ECサイト]     │ [ブログ]       │ [コーポレート]  │               │
│  └────────────────┴────────────────┴────────────────┘               │
│                                                                       │
│  プリセット                                                          │
│  ┌────────────────┬────────────────┬────────────────┐               │
│  │ [SEOフィールド] │ [住所フィールド] │ [SNSリンク]    │               │
│  └────────────────┴────────────────┴────────────────┘               │
└──────────────────────────────────────────────────────────────────────┘
```

### フィールドビルダー

```
┌──────────────────────────────────────────────────────────────────────┐
│  商品 (product) の編集                            [保存] [キャンセル] │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  基本設定                                                            │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ 名前: product              ラベル: 商品                         │ │
│  │ 複数形: 商品               アイコン: 📦                         │ │
│  │ ☑ 管理メニューに表示  ☑ 検索可能  ☑ REST API公開               │ │
│  │ ☑ リビジョン有効  ワークフロー: [content_review ▼]              │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  フィールド                                              [+ 追加 ▼]  │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                                                                  │ │
│  │  ≡ 商品名 (name)                                                │ │
│  │    string | 必須 | 一覧表示 | 検索対象                    [編集]│ │
│  │                                                                  │ │
│  │  ≡ スラッグ (slug)                                              │ │
│  │    slug | 必須 | ユニーク                                 [編集]│ │
│  │                                                                  │ │
│  │  ≡ 価格 (price)                                                 │ │
│  │    money | 必須 | 一覧表示                                [編集]│ │
│  │                                                                  │ │
│  │  ≡ 商品タイプ (product_type)                                    │ │
│  │    select | 物理商品 / デジタル / サービス               [編集]│ │
│  │                                                                  │ │
│  │  ≡ 重量 (weight)                                                │ │
│  │    float | 条件: product_type = physical                  [編集]│ │
│  │                                                                  │ │
│  │  ▼ 仕様 (specifications)                                        │ │
│  │    repeater | 0-20行                                      [編集]│ │
│  │    ├─ 項目名 (key) - string | 必須                              │ │
│  │    └─ 値 (value) - string | 必須                                │ │
│  │                                                                  │ │
│  │  ▼ 商品詳細 (sections)                                          │ │
│  │    flexible | テキスト / 画像 / 動画                      [編集]│ │
│  │                                                                  │ │
│  │  ▼ 配送情報 (shipping)                                          │ │
│  │    group | 3フィールド                                    [編集]│ │
│  │                                                                  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  プリセット適用                                                      │
│  [+ SEOフィールド] [+ タイムスタンプ]                                │
│                                                                       │
│  リレーション                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ • product_category: category (多対多)                           │ │
│  │ • product_tags: tag (多対多)                                    │ │
│  │ • related_products: product (多対多、自己参照)                  │ │
│  │                                                [+ リレーション追加]│ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  [変更履歴を表示]  [YAMLエクスポート]  [削除（データも削除されます）] │
└──────────────────────────────────────────────────────────────────────┘
```

---

## スキーマバージョン管理とマイグレーション

### バージョン管理

```python
@dataclass
class ContentTypeVersion:
    """コンテンツタイプのバージョン"""
    version: int
    content_type: str
    schema: dict  # YAMLの内容
    created_at: datetime
    created_by: str
    change_summary: str

    # 差分
    added_fields: list[str]
    removed_fields: list[str]
    modified_fields: list[FieldChange]


class ContentTypeVersionManager:
    """バージョン管理"""

    async def save_version(
        self,
        content_type: str,
        schema: dict,
        user_id: str,
    ) -> ContentTypeVersion:
        """新しいバージョンを保存"""

        # 現在のバージョンを取得
        current = await self.get_current_version(content_type)

        # 差分を計算
        diff = self._calculate_diff(current.schema if current else {}, schema)

        # スキーマ検証（循環参照チェック等）
        await self._validate_schema(schema)

        # 新バージョン作成
        new_version = ContentTypeVersion(
            version=(current.version + 1) if current else 1,
            content_type=content_type,
            schema=schema,
            created_at=datetime.utcnow(),
            created_by=user_id,
            change_summary=self._generate_summary(diff),
            added_fields=diff.added,
            removed_fields=diff.removed,
            modified_fields=diff.modified,
        )

        # 自動バックアップ
        await self._create_backup(content_type)

        await self._save(new_version)
        return new_version

    async def _validate_schema(self, schema: dict) -> None:
        """スキーマを検証"""

        # 循環参照チェック
        if self._has_circular_reference(schema):
            raise ValueError("Circular reference detected in schema")

        # フィールド名の重複チェック
        field_names = [f['name'] for f in schema.get('fields', [])]
        if len(field_names) != len(set(field_names)):
            raise ValueError("Duplicate field names detected")

        # リレーション先の存在チェック
        for field in schema.get('fields', []):
            if field['type'] in ('relation', 'relations'):
                target = field.get('target')
                if target and not await self._content_type_exists(target):
                    raise ValueError(f"Relation target '{target}' does not exist")
```

### 自動マイグレーション

```python
class SchemaMigrator:
    """スキーマ変更時のデータマイグレーション"""

    async def migrate(
        self,
        content_type: str,
        old_schema: dict,
        new_schema: dict,
        options: MigrationOptions,
    ) -> MigrationResult:
        """データマイグレーションを実行"""

        result = MigrationResult()

        # 差分を分析
        diff = self._analyze_diff(old_schema, new_schema)

        # 追加されたフィールド（デフォルト値を設定）
        for field_name in diff.added:
            field_def = self._get_field_def(new_schema, field_name)
            default = field_def.get('default')

            if default is not None:
                count = await self._set_default_value(
                    content_type, field_name, default
                )
                result.add_migration(field_name, 'set_default', count)

        # 削除されたフィールド
        for field_name in diff.removed:
            if options.delete_removed_fields:
                count = await self._delete_field_data(content_type, field_name)
                result.add_migration(field_name, 'deleted', count)
            else:
                # 削除せずにマーク
                result.add_warning(
                    f"Field '{field_name}' is no longer in schema but data retained"
                )

        # 型が変更されたフィールド
        for change in diff.type_changes:
            if self._can_convert(change.old_type, change.new_type):
                count = await self._convert_field_type(
                    content_type,
                    change.field_name,
                    change.old_type,
                    change.new_type,
                )
                result.add_migration(change.field_name, 'type_converted', count)
            else:
                result.add_error(
                    f"Cannot convert '{change.field_name}' from {change.old_type} to {change.new_type}"
                )

        return result
```

---

## クエリビルダー

### 高度な検索

```python
class EntityQueryBuilder:
    """エンティティ検索クエリビルダー"""

    def __init__(self, db: AsyncSession, content_type: str):
        self.db = db
        self.content_type = content_type
        self._filters = []
        self._orders = []
        self._includes = []
        self._selects = []
        self._limit = 100
        self._offset = 0

    # フィルタ
    def where(self, field: str, op: str, value: Any) -> 'EntityQueryBuilder':
        self._filters.append(WhereClause(field, op, value))
        return self

    def where_in(self, field: str, values: list) -> 'EntityQueryBuilder':
        return self.where(field, 'in', values)

    def where_between(self, field: str, min_val: Any, max_val: Any) -> 'EntityQueryBuilder':
        return self.where(field, 'between', (min_val, max_val))

    def where_json(self, field: str, path: str, op: str, value: Any) -> 'EntityQueryBuilder':
        """JSON内のフィールド検索"""
        self._filters.append(JsonWhereClause(field, path, op, value))
        return self

    def where_full_text(self, query: str, fields: list[str] = None) -> 'EntityQueryBuilder':
        """全文検索"""
        self._filters.append(FullTextClause(query, fields))
        return self

    def where_has_relation(self, relation: str, callback: Callable = None) -> 'EntityQueryBuilder':
        """リレーションが存在する"""
        self._filters.append(HasRelationClause(relation, callback))
        return self

    # ソート
    def order_by(self, field: str, direction: str = 'asc') -> 'EntityQueryBuilder':
        self._orders.append(OrderClause(field, direction))
        return self

    # リレーション
    def include(self, *relations: str) -> 'EntityQueryBuilder':
        """リレーションをプリロード"""
        self._includes.extend(relations)
        return self

    def include_count(self, relation: str, alias: str = None) -> 'EntityQueryBuilder':
        """リレーション数をカウント"""
        self._includes.append(CountRelation(relation, alias))
        return self

    # ページネーション
    def paginate(self, page: int, per_page: int = 20) -> 'EntityQueryBuilder':
        self._limit = per_page
        self._offset = (page - 1) * per_page
        return self

    # 実行
    async def get(self) -> list[Entity]:
        """クエリ実行"""
        query = await self._build_query()
        result = await self.db.execute(query)
        entities = result.scalars().all()

        if self._includes:
            await self._load_relations(entities)

        return entities

    async def first(self) -> Entity | None:
        self._limit = 1
        results = await self.get()
        return results[0] if results else None

    async def count(self) -> int:
        query = await self._build_count_query()
        result = await self.db.execute(query)
        return result.scalar()

    async def sum(self, field: str) -> float:
        return await self.aggregate(field, 'SUM')

    async def avg(self, field: str) -> float:
        return await self.aggregate(field, 'AVG')


# 使用例
products = await (
    EntityQueryBuilder(db, 'product')
    .where('status', '=', 'published')
    .where('price', '>=', 1000)
    .where('price', '<=', 5000)
    .where_json('shipping', '$.weight', '<', 10)
    .where_has_relation('categories', lambda q: q.where('slug', '=', 'electronics'))
    .include('categories', 'related_products')
    .include_count('reviews', 'review_count')
    .order_by('price', 'asc')
    .paginate(page=1, per_page=20)
    .get()
)
```

---

## REST API

### 自動生成API

```python
# 自動生成されるエンドポイント
# GET    /api/{content_type}          - 一覧
# GET    /api/{content_type}/{id}     - 詳細
# POST   /api/{content_type}          - 作成
# PUT    /api/{content_type}/{id}     - 更新
# DELETE /api/{content_type}/{id}     - 削除

# クエリパラメータ
# ?fields=name,price,category  - 取得フィールド指定
# ?include=categories,reviews  - リレーションを含める
# ?filter[status]=published    - フィルタ
# ?filter[price][gte]=1000     - 演算子付きフィルタ
# ?sort=-created_at,name       - ソート（-は降順）
# ?page=1&per_page=20          - ページネーション
# ?search=keyword              - 全文検索


class ContentTypeAPIRouter:
    """コンテンツタイプ用の動的APIルーター"""

    def generate_routes(self, content_type: ContentType) -> APIRouter:
        router = APIRouter(prefix=f"/{content_type.name}", tags=[content_type.label])

        # レート制限
        limiter = RateLimiter(
            max_requests=content_type.api_rate_limit or 100,
            window_seconds=60,
        )

        @router.get("", response_model=PaginatedResponse)
        @limiter.limit
        async def list_entities(
            request: Request,
            fields: str = None,
            include: str = None,
            sort: str = "-created_at",
            page: int = 1,
            per_page: int = Query(default=20, le=100),
            db: AsyncSession = Depends(get_db),
            user: User = Depends(get_current_user),
        ):
            query = EntityQueryBuilder(db, content_type.name)

            # フィルタ適用
            for key, value in request.query_params.items():
                if key.startswith('filter['):
                    field, op = self._parse_filter_key(key)
                    query.where(field, op, value)

            # 検索
            if request.query_params.get('search'):
                query.where_full_text(request.query_params['search'])

            # ソート
            for sort_field in sort.split(','):
                direction = 'desc' if sort_field.startswith('-') else 'asc'
                field = sort_field.lstrip('-')
                query.order_by(field, direction)

            # リレーション
            if include:
                query.include(*include.split(','))

            # ページネーション
            total = await query.count()
            entities = await query.paginate(page, per_page).get()

            # フィールド権限でフィルタ
            data = [
                await self.permission_svc.filter_readable_fields(e, user)
                for e in entities
            ]

            return PaginatedResponse(
                data=data,
                meta={
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': (total + per_page - 1) // per_page,
                },
            )

        return router
```

### TypeScript型定義エクスポート

```python
class TypeScriptExporter:
    """TypeScript型定義を生成"""

    def export(self, content_types: list[ContentType]) -> str:
        """全コンテンツタイプの型定義を生成"""

        output = []
        output.append("// Auto-generated by Focomy")
        output.append("")

        for ct in content_types:
            output.append(self._generate_interface(ct))
            output.append("")

        return "\n".join(output)

    def _generate_interface(self, ct: ContentType) -> str:
        """インターフェースを生成"""

        lines = [f"export interface {self._to_pascal_case(ct.name)} {{"]

        for field in ct.fields:
            ts_type = self._map_type(field['type'])
            optional = "" if field.get('required') else "?"
            lines.append(f"  {field['name']}{optional}: {ts_type};")

        lines.append("}")

        return "\n".join(lines)

    TYPE_MAP = {
        'string': 'string',
        'text': 'string',
        'number': 'number',
        'float': 'number',
        'boolean': 'boolean',
        'date': 'string',
        'datetime': 'string',
        'email': 'string',
        'url': 'string',
        'select': 'string',
        'multiselect': 'string[]',
        'image': 'Media',
        'file': 'Media',
        'gallery': 'Media[]',
        'relation': 'string',
        'relations': 'string[]',
        'repeater': 'any[]',
        'flexible': 'any[]',
        'group': 'Record<string, any>',
        'json': 'Record<string, any>',
    }

    def _map_type(self, field_type: str) -> str:
        return self.TYPE_MAP.get(field_type, 'any')
```

### JSON Schema/OpenAPI エクスポート

```python
class OpenAPIExporter:
    """OpenAPI仕様を生成"""

    def export(self, content_types: list[ContentType]) -> dict:
        """OpenAPI仕様を生成"""

        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Focomy API",
                "version": "1.0.0",
            },
            "paths": {},
            "components": {
                "schemas": {},
            },
        }

        for ct in content_types:
            if not ct.api_enabled:
                continue

            # スキーマを追加
            spec["components"]["schemas"][ct.name] = self._generate_schema(ct)

            # パスを追加
            spec["paths"].update(self._generate_paths(ct))

        return spec

    def _generate_schema(self, ct: ContentType) -> dict:
        """JSONスキーマを生成"""

        properties = {}
        required = []

        for field in ct.fields:
            properties[field['name']] = self._field_to_json_schema(field)
            if field.get('required'):
                required.append(field['name'])

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
```

---

## Webhook連携

```yaml
# content_types/product.yaml
webhooks:
  - event: created
    url: https://example.com/webhooks/product-created
    secret: ${WEBHOOK_SECRET}
    retry: 3

  - event: updated
    url: https://example.com/webhooks/product-updated
    # 特定フィールドが変更された場合のみ
    fields: [price, stock]

  - event: deleted
    url: https://example.com/webhooks/product-deleted

  - event: status_changed
    url: https://example.com/webhooks/product-published
    conditions:
      - field: status
        from: draft
        to: published
```

---

## データエクスポート/インポート

```python
class ContentExporter:
    """コンテンツエクスポート"""

    async def export_csv(
        self,
        content_type: str,
        filters: dict = None,
        fields: list[str] = None,
    ) -> StreamingResponse:
        """CSV形式でエクスポート"""

    async def export_json(
        self,
        content_type: str,
        filters: dict = None,
        include_relations: bool = True,
    ) -> StreamingResponse:
        """JSON形式でエクスポート"""

    async def export_excel(
        self,
        content_type: str,
        filters: dict = None,
    ) -> StreamingResponse:
        """Excel形式でエクスポート"""


class ContentImporter:
    """コンテンツインポート"""

    async def import_csv(
        self,
        content_type: str,
        file: UploadFile,
        options: ImportOptions,
    ) -> ImportResult:
        """CSVからインポート"""

    async def import_json(
        self,
        content_type: str,
        file: UploadFile,
        options: ImportOptions,
    ) -> ImportResult:
        """JSONからインポート"""
```

---

## シーダー（テストデータ生成）

```python
class EntitySeeder:
    """テストデータ生成"""

    async def seed(
        self,
        content_type: str,
        count: int = 10,
        locale: str = 'ja_JP',
    ) -> list[Entity]:
        """テストデータを生成"""

        fake = Faker(locale)
        ct = await self.get_content_type(content_type)

        entities = []

        for _ in range(count):
            data = {}

            for field in ct.fields:
                data[field['name']] = self._generate_value(field, fake)

            entity = await self.entity_svc.create(content_type, data)
            entities.append(entity)

        return entities

    def _generate_value(self, field: dict, fake: Faker) -> Any:
        """フィールドタイプに応じた値を生成"""

        field_type = field['type']

        generators = {
            'string': lambda: fake.sentence(nb_words=5),
            'text': lambda: fake.paragraph(nb_sentences=3),
            'number': lambda: fake.random_int(min=1, max=1000),
            'float': lambda: fake.pyfloat(min_value=0, max_value=1000, right_digits=2),
            'boolean': lambda: fake.boolean(),
            'date': lambda: fake.date_this_year(),
            'datetime': lambda: fake.date_time_this_year(),
            'email': lambda: fake.email(),
            'url': lambda: fake.url(),
            'phone': lambda: fake.phone_number(),
            'money': lambda: Decimal(fake.random_int(min=100, max=10000)),
            'color': lambda: fake.hex_color(),
            'slug': lambda: fake.slug(),
        }

        generator = generators.get(field_type, lambda: None)
        return generator()
```

---

## パフォーマンス最適化

### インデックス推奨

```python
class IndexRecommender:
    """インデックス推奨"""

    async def analyze(self, content_type: str) -> list[IndexRecommendation]:
        """クエリパターンを分析してインデックスを推奨"""

        recommendations = []

        # クエリログを分析
        query_patterns = await self._get_query_patterns(content_type)

        for pattern in query_patterns:
            # 頻繁に使われるフィルタ条件
            if pattern.frequency > 100:
                if not await self._has_index(content_type, pattern.field):
                    recommendations.append(IndexRecommendation(
                        field=pattern.field,
                        reason=f"Frequently used in queries ({pattern.frequency} times)",
                        estimated_improvement="50-80%",
                    ))

        return recommendations

    async def apply_recommendation(self, recommendation: IndexRecommendation) -> None:
        """インデックスを作成"""
        await self.db.execute(
            f"CREATE INDEX idx_{recommendation.content_type}_{recommendation.field} "
            f"ON entity_values (content_type, field_name, value_string) "
            f"WHERE content_type = '{recommendation.content_type}' "
            f"AND field_name = '{recommendation.field}'"
        )
```

### 遅いクエリ検出

```python
class SlowQueryDetector:
    """遅いクエリ検出"""

    THRESHOLD_MS = 100

    async def detect(self, since: datetime = None) -> list[SlowQuery]:
        """遅いクエリを検出"""

        result = await self.db.execute(
            select(query_logs)
            .where(
                query_logs.c.duration_ms > self.THRESHOLD_MS,
                query_logs.c.created_at >= since if since else True,
            )
            .order_by(query_logs.c.duration_ms.desc())
            .limit(100)
        )

        return result.fetchall()

    async def get_optimization_suggestions(self, query: SlowQuery) -> list[str]:
        """最適化提案を返す"""

        suggestions = []

        # EXPLAIN結果を分析
        explain = await self.db.execute(f"EXPLAIN ANALYZE {query.sql}")

        if 'Seq Scan' in str(explain):
            suggestions.append("Consider adding an index on the filtered columns")

        if 'Sort' in str(explain) and 'Index' not in str(explain):
            suggestions.append("Consider adding an index on the sorted columns")

        return suggestions
```

---

## ファイル構成

```
core/
├── services/
│   ├── content_type/
│   │   ├── __init__.py
│   │   ├── builder.py          # コンテンツタイプビルダー
│   │   ├── version.py          # バージョン管理
│   │   ├── migrator.py         # マイグレーション
│   │   ├── starter_kit.py      # スターターキット
│   │   └── exporter.py         # YAMLエクスポート
│   ├── field/
│   │   ├── __init__.py
│   │   ├── types.py            # フィールドタイプ定義
│   │   ├── validators.py       # バリデーター
│   │   ├── renderers.py        # UIレンダラー
│   │   ├── converters.py       # 型変換
│   │   └── permissions.py      # フィールド権限
│   ├── query/
│   │   ├── __init__.py
│   │   ├── builder.py          # クエリビルダー
│   │   └── clauses.py          # WHERE句など
│   ├── formula/
│   │   ├── __init__.py
│   │   └── engine.py           # 計算フィールドエンジン
│   ├── revision/
│   │   ├── __init__.py
│   │   └── manager.py          # リビジョン管理
│   ├── workflow/
│   │   ├── __init__.py
│   │   └── service.py          # ワークフロー
│   ├── schedule/
│   │   ├── __init__.py
│   │   └── service.py          # スケジュール公開
│   ├── audit/
│   │   ├── __init__.py
│   │   └── logger.py           # 監査ログ
│   ├── lock/
│   │   ├── __init__.py
│   │   └── service.py          # 編集ロック
│   ├── webhook/
│   │   ├── __init__.py
│   │   └── dispatcher.py       # Webhook配信
│   ├── seeder/
│   │   ├── __init__.py
│   │   └── generator.py        # テストデータ生成
│   └── performance/
│       ├── __init__.py
│       ├── index.py            # インデックス推奨
│       └── slow_query.py       # 遅いクエリ検出
├── api/
│   ├── content_types.py        # コンテンツタイプAPI
│   ├── entities.py             # エンティティAPI
│   ├── revisions.py            # リビジョンAPI
│   └── export.py               # エクスポートAPI
└── templates/
    └── admin/
        └── content_type/
            ├── index.html      # 一覧
            ├── builder.html    # ビルダー
            ├── field_modal.html # フィールド編集
            ├── versions.html   # バージョン履歴
            ├── revisions.html  # リビジョン履歴
            └── workflow.html   # ワークフロー設定
```

---

## 実装優先度

| Phase | 機能 | 説明 |
|-------|------|------|
| 1 | 基本フィールド拡張 | money, phone, color, range |
| 2 | 選択フィールド | select, multiselect, radio, checkbox |
| 3 | メディアフィールド | image, file, gallery（強化） |
| 4 | リピーター | repeater フィールドタイプ |
| 5 | フレキシブル | flexible フィールドタイプ |
| 6 | グループ | group フィールドタイプ |
| 7 | 条件付きロジック | 表示/必須の条件 |
| 8 | コンテンツタイプビルダーUI | Admin画面でコンテンツタイプを作成 |
| 9 | 計算フィールド | calculated, lookup |
| 10 | 高度なバリデーション | カスタム、非同期 |
| 11 | クエリビルダー | 高度な検索・フィルタ |
| 12 | バージョン管理 | スキーマ履歴、ロールバック |
| 13 | マイグレーション | 自動データ移行 |
| 14 | リビジョン履歴 | エンティティの変更履歴 |
| 15 | ワークフロー | 承認フロー |
| 16 | スケジュール公開 | 予約公開・非公開 |
| 17 | フィールド権限 | 読み書き権限制御 |
| 18 | 監査ログ | 変更履歴の記録 |
| 19 | 編集ロック | 同時編集防止 |
| 20 | Webhook | イベント通知 |
| 21 | エクスポート/インポート | CSV, JSON, Excel |
| 22 | TypeScript/OpenAPI | 型定義エクスポート |
| 23 | シーダー | テストデータ生成 |
| 24 | パフォーマンス | インデックス推奨、遅いクエリ検出 |
| 25 | スターターキット | 業種別テンプレート |
| 26 | GraphQL | オプション対応 |
