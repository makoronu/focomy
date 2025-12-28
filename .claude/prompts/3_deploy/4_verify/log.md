# 完了ログ

## やること
1. CLAUDE.md 更新（リリース情報追加）
2. git tag 作成
3. GitHubリポジトリ作成（未作成の場合）
4. git push --tags

---

## コマンド

### CLAUDE.md 更新
リリースセクションにバージョン・日付・リンクを追加

### git tag
```bash
git tag vx.x.x
```

### GitHubリポジトリ（初回のみ）
```bash
# リポジトリ作成 & プッシュ
gh repo create focomy --public --description "The Most Beautiful CMS" --source=. --push

# または既存リポジトリにプッシュ
git remote add origin https://github.com/USERNAME/focomy.git
git push -u origin main
```

### タグプッシュ
```bash
git push --tags
```

---

## 完了条件
- [ ] CLAUDE.md にリリース情報追加
- [ ] タグ作成・プッシュ
- [ ] GitHubリポジトリにコード公開

## 次 → 終了（_main.md 完了報告）
