# 外部連携

## freee
- コンソール: https://app.secure.freee.co.jp/developers/applications
- リダイレクトURI: `https://sas.realestateautomation.net/api/auth/freee/callback`
- 401エラー → 再認証が必要

## Dropbox
- コンソール: https://www.dropbox.com/developers/apps

## 障害時ルール
- 外部API障害 → 業務止めない
- リトライ: 3回、exponential backoff
- 失敗時: 通知 + 手動対応キューへ

## 次の工程
→ verify.md
