# 出力

## やること
- HTML形式でマニュアル生成
- PDF印刷用も出力

## 注意
- **スクショは含めない**（テキストのみ）
- デザインは既存テンプレート踏襲

## 構造
```
manuals/
├── html/
│   ├── index.html
│   └── {page}/
│       └── {flow}.html
└── pdf/
    └── {page}_{flow}.pdf
```

## 完了条件
- 全フローのHTML/PDFあり
- スクショなし
