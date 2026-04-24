# article-writer スキル

公営住宅に関する情報記事を生成してD1に保存する手順。

## 実行前チェック
1. `wrangler d1 execute kouei-db --command "SELECT slug FROM articles WHERE category='article' ORDER BY published_at DESC LIMIT 10"` で最新の記事slugを確認する
2. 同じテーマの記事が存在しないことを確認する

## 記事テーマの選定（手続き・Q&A系に特化）
比較・制度解説はguide-writerの担当。article-writerは「具体的な手順・よくある疑問」に絞る。

テーマ候補（未執筆のものを優先）:
- 申し込み手順系: 「UR賃貸の申し込みに必要な書類一覧」「JKKの抽選に申し込む手順」「都営住宅の申し込み時期と締め切り」
- 審査対策系: 「UR審査で落ちる理由と対策」「公営住宅の収入基準を確認する方法」
- 生活Q&A系: 「公営住宅でペットは飼える？UR・JKK・都営を比較」「公営住宅の更新料はかかる？」「UR賃貸を退去するときの手続き」
- 費用系: 「UR賃貸の初期費用はいくら？」「都営住宅の家賃はどう決まる？」

## 記事フォーマット
```markdown
## [冒頭: 読者の悩みに共感する1〜2文]

[このページでわかること（3点箇条書き）]

## [見出し1]
[内容]

## [見出し2]
[内容]

## まとめ
[要点3点と次のアクション]
```

## slug の命名規則
- 英数字とハイフンのみ（例: `ur-application-guide`, `jkk-lottery-system`）
- 記事内容を表す英語で30文字以内

## D1への保存
```sql
INSERT INTO articles (slug, title, meta_description, body, category, published_at)
VALUES (?, ?, ?, ?, 'article', CURRENT_TIMESTAMP)
```

wranglerコマンドで実行:
```bash
wrangler d1 execute kouei-db --command "INSERT INTO articles ..."
```

## agent_runs への記録
```sql
INSERT INTO agent_runs (agent_name, status, records_processed, finished_at)
VALUES ('article-writer', 'success', 1, CURRENT_TIMESTAMP)
```

## 失敗時
- statusを'failure'にしてerror_messageに原因を記録する
- 記事本文が1000字未満の場合は品質不足として保存しない
