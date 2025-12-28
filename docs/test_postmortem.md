# テスト問題のポストモーテム

## 問題
pytest 実行時に 37 テストが失敗（28 は成功）

## 根本原因

### 1. テストが架空のAPIを想定していた

テストコードが実装されていないメソッドを呼び出していた：

| ファイル | 呼び出されたメソッド | 実際の実装 |
|----------|---------------------|------------|
| test_field_service.py | `validate_field(field_def, value)` | 存在しない |
| test_field_service.py | `serialize_value(field_def, value)` | 存在しない |
| test_field_service.py | `deserialize_value(field_def, value)` | 存在しない |
| test_entity_service.py | `list(type_name, limit)` | `find()` を使うべき |
| test_auth_service.py | `use_backup_code(user_id, code)` | `verify_totp()` 内で処理 |

### 2. なぜこうなったか（5 Whys）

```
Why 1: テストが失敗した
Why 2: テストが存在しないメソッドを呼んでいた
Why 3: テストが「将来のAPI」を想定して書かれた
Why 4: 実装とテストが同期していなかった
Why 5: TDDを採用せず、テストを後から書いた
```

### 3. 教訓

1. **テストは実装と同時に書く**（TDD または実装直後）
2. **架空のAPIでテストを書かない**
3. **テストは定期的に実行する**（CI/CDで自動化）

## 対応

テストを実装に合わせて修正：

1. `test_field_service.py` - 全面書き換え（FieldDefinition, ContentType モデルのテスト）
2. `test_entity_service.py` - 引数名・メソッド名の修正
3. `test_auth_service.py` - 戻り値型・メソッド名の修正

## 結果

- Before: 28 passed, 37 failed
- After: 72 passed, 0 failed

## 再発防止

1. **CI/CD でテスト実行**（.github/workflows/ci.yml 設定済み）
2. **PR マージ前にテスト必須**
3. **カバレッジ監視**（Codecov 連携済み）
