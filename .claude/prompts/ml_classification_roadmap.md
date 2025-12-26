# 勘定科目ML分類器 ロードマップ

## 概要
Claude OCR（読み取り） + MLモデル（分類）のハイブリッド構成

## Phase 1: データ収集（1-2日）
- [ ] freee APIから過去仕訳を取得するスクリプト作成
- [ ] 取得項目: 取引先名、摘要、金額、税区分、勘定科目
- [ ] データクレンジング（欠損値処理、正規化）
- [ ] 目標: 最低1000件、理想5000件以上

## Phase 2: モデル構築（1日）
- [ ] 特徴量エンジニアリング
  - テキスト: TF-IDF or CountVectorizer
  - 金額: 正規化 or カテゴリ化（小額/中額/高額）
- [ ] モデル選定（候補）
  - RandomForest（シンプル、解釈しやすい）
  - LightGBM（高速、高精度）
  - ロジスティック回帰（ベースライン）
- [ ] 学習・評価（train/test split, cross-validation）
- [ ] 目標精度: 80%以上

## Phase 3: 統合（1日）
- [ ] モデルをpickle/joblib形式で保存
- [ ] 推論サービス作成（app/services/ml_classifier.py）
- [ ] vouchers.pyのOCR後処理に組み込み
- [ ] フォールバック: ML信頼度低い場合は既存ルール併用

## Phase 4: 運用（継続）
- [ ] 定期再学習（月1回など）
- [ ] 精度モニタリング
- [ ] ユーザー修正からのフィードバックループ

## ファイル構成
```
backend/
├── app/
│   ├── services/
│   │   ├── ml_classifier.py    # 推論
│   │   └── ml_trainer.py       # 学習
│   └── ml_models/
│       └── account_classifier.joblib
├── scripts/
│   ├── fetch_training_data.py  # freeeからデータ取得
│   └── train_model.py          # モデル学習
```

## 依存パッケージ
```
scikit-learn
pandas
joblib
```

## 期待効果
- 推論速度: 5-8秒 → 10ミリ秒以下
- API費用: 毎回課金 → 0円
- 精度: 御社データに最適化
