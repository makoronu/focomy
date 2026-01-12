# pip インストールテスト

## チェック
- [ ] `pip install focomy` 成功
- [ ] `focomy init testsite` で `content_types/` なし、`plugins/` あり
- [ ] `focomy serve` 起動、`/api/health` 応答
- [ ] テンプレート6種存在（base/home/post/category/archive/search）
- [ ] **pip upgrade後も動作**（コア定義がパッケージから読み込まれる）

## 中断条件
- content_types/が作成された → アーキテクチャ違反

## 次 → log.md
