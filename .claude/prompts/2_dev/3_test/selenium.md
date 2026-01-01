# Seleniumテスト

## テスト環境（必須）
- **ローカル環境は使用禁止**
- サブドメイン環境を使用: `4690.tuishou.info`
- VPS: `160.251.196.103`
- SSH: `ssh -i ~/.ssh/conoha_suishu.pem root@160.251.196.103`
- focomyソース: `/var/www/new_hp/focomy_src` (git clone済み)
- サイトディレクトリ: `/var/www/new_hp/shirokuma_hp`

## 更新時の手順
```bash
ssh -i ~/.ssh/conoha_suishu.pem root@160.251.196.103
cd /var/www/new_hp/focomy_src && git pull
source /var/www/new_hp/venv/bin/activate
pip install -e /var/www/new_hp/focomy_src
# 設定ファイルを同期（重要！）
cp /var/www/new_hp/focomy_src/content_types/*.yaml /var/www/new_hp/shirokuma_hp/content_types/
cp /var/www/new_hp/focomy_src/relations.yaml /var/www/new_hp/shirokuma_hp/
cp /var/www/new_hp/focomy_src/config.yaml /var/www/new_hp/shirokuma_hp/  # features:セクション含む
pkill -f focomy
cd /var/www/new_hp/shirokuma_hp && focomy serve --port 8080
```

## やること
1. 変更した画面を開く
2. 操作をシミュレート
3. スクリーンショット保存
4. 問題がないか確認
5. **問題発見時：原因を精査**

## テストコード例
```python
from selenium import webdriver
driver = webdriver.Chrome()
driver.set_page_load_timeout(10)
driver.get("http://localhost:3002/対象画面")
driver.save_screenshot("test_screenshots/xxx.png")
```

## 完了条件
- [ ] スクショ取得した
- [ ] 画面崩れなし
- [ ] 動作正常

## 中断条件（即停止→報告）
- 画面崩れ
- エラー表示
- 動作不良

## 問題発見時の精査手順

問題を発見したら、以下を確認して原因を特定する：

1. **テスト環境の問題か？**
   - 設定ファイル（content_types/*.yaml, relations.yaml, config.yaml）が最新か
   - config.yamlのfeatures:セクションが正しいか（新機能テスト時は特に重要）
   - サーバーが正しく再起動されているか
   - キャッシュが残っていないか

2. **Focomyコードの問題か？**
   - テンプレートの修正漏れ
   - ロジックのバグ
   - 修正がビルド/デプロイに含まれていない

3. **精査結果をレポートに含める**
   - 原因がテスト環境 → 環境を修正して再テスト
   - 原因がFocomyコード → Issueに報告

## 次の工程
→ doc_update.md
