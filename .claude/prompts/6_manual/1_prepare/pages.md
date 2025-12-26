# 対象ページ定義

## やること
- `config/manual_pages.yaml` に対象ページを列挙
- ページごとに目的・操作フローを定義

## 形式
```yaml
- path: /vouchers
  name: 出金証憑処理
  flows:
    - name: 証憑を処理する
      steps: [フォルダ選択, 証憑選択, 入力, 登録]
```

## 完了条件
- 全ページがyamlに定義済み

## 次 → terms.md
