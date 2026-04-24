# guide-writer スキル

公営住宅に関する包括的なガイドを生成してD1に保存する手順。

## 実行前チェック
1. `wrangler d1 execute kouei-db --command "SELECT slug FROM articles WHERE category='guide' ORDER BY published_at DESC LIMIT 10"` で最新のガイドslugを確認する
2. 同じテーマのガイドが存在しないことを確認する

## ガイドテーマの選定（制度理解・意思決定支援系に特化）
手順・Q&Aはarticle-writerの担当。guide-writerは「制度の全体像・どれを選ぶべきかの意思決定」に絞る。

テーマ候補（未執筆のものを優先）:
1. 「UR賃貸住宅 完全ガイド｜メリット・デメリット・向いている人」
2. 「JKK東京 完全ガイド｜審査・家賃・優遇制度まとめ」
3. 「都営住宅 完全ガイド｜申し込み資格・抽選倍率・生活実態」
4. 「公営住宅の審査条件・収入基準を徹底解説」
5. 「東京都で家賃を抑えて住む方法【公営住宅活用ガイド】」

## ガイドフォーマット
```markdown
## このガイドを読むとわかること
- [ポイント1]
- [ポイント2]
- [ポイント3]

## [セクション1: 概要・背景]
[内容]

## [セクション2: 具体的な手順・条件]
[内容（箇条書き推奨）]

## [セクション3: 注意点・よくある質問]
[内容]

## [セクション4: まとめと次のステップ]
[要点と公式サイトへの誘導]

> ※ 申し込み条件・収入基準・家賃は変更される場合があります。最新情報は各公式サイトでご確認ください。
```

## slug の命名規則
- 英数字とハイフンのみ（例: `ur-complete-guide`, `kouei-jutaku-types`）
- 30文字以内

## D1への保存
```sql
INSERT INTO articles (slug, title, meta_description, body, category, published_at)
VALUES (?, ?, ?, ?, 'guide', CURRENT_TIMESTAMP)
```

## agent_runs への記録
```sql
INSERT INTO agent_runs (agent_name, status, records_processed, finished_at)
VALUES ('guide-writer', 'success', 1, CURRENT_TIMESTAMP)
```

## 失敗時
- statusを'failure'にしてerror_messageに原因を記録する
- 本文が1500字未満の場合は品質不足として保存しない
