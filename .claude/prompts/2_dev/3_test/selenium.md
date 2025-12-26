# Seleniumテスト

## やること
1. 変更した画面を開く
2. 操作をシミュレート
3. スクリーンショット保存
4. 問題がないか確認

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

## 次の工程
→ doc_update.md
