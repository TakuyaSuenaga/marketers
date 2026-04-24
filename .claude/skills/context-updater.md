# context-updater スキル

CLAUDE.md の「学習済みインサイト」セクションをデータに基づいて更新し、git commit する手順。

## ステップ1：データ収集

### 記事パフォーマンス（articlesテーブル）
```bash
cd workers && wrangler d1 execute kouei-db --remote --command \
  "SELECT slug, title, category, published_at FROM articles ORDER BY published_at DESC LIMIT 20"
```

### エージェント実行ログ（直近7日）
```bash
cd workers && wrangler d1 execute kouei-db --remote --command \
  "SELECT agent_name, status, records_processed, started_at FROM agent_runs WHERE started_at > datetime('now', '-7 days') ORDER BY started_at DESC"
```

### GSCデータ（設定済みの場合のみ）
GSC_CREDENTIALSが設定されている場合、直近28日間の以下を取得：
- クリック数上位10キーワード
- 表示回数100以上・CTR3%未満のページ（改善候補）
- 直近7日で新たにランクインしたキーワード

## ステップ2：インサイト生成

収集したデータをもとに、以下の観点でインサイトを文章化する：

1. **効果が出ているコンテンツパターン**（あれば）
   - どんなタイトル構造が高CTRか
   - どのStageのキーワードで流入が多いか

2. **優先すべき未開拓テーマ**
   - GSCで表示されているが記事がないキーワード
   - articlesテーブルにないStage2/3テーマ

3. **避けるべきパターン**
   - 重複しているテーマ
   - CTRが低いタイトルの傾向

## ステップ3：CLAUDE.md の更新

CLAUDE.md を読み込み、`## 学習済みインサイト（自動更新）` セクションを以下の形式で**全体を上書き**する：

```markdown
## 学習済みインサイト（自動更新）

最終更新: YYYY-MM-DD

### 効果が出ているパターン
- （データがあれば記載、なければ「計測開始前」）

### 優先すべき未開拓テーマ
- （具体的なキーワード・テーマ名）

### 避けるべきパターン
- （具体的な傾向）
```

他のセクション（サイト基本情報・ターゲットキーワード・競合・コンテンツガイドライン・技術スタック）は**絶対に変更しない**。

## ステップ4：git commit

```bash
git config user.email "agents@kouei-navi"
git config user.name "context-updater"
git add CLAUDE.md
git commit -m "chore: CLAUDE.md 学習済みインサイトを自動更新 $(date +%Y-%m-%d)"
```

## ステップ5：agent_runs に記録

```bash
cd workers && wrangler d1 execute kouei-db --remote --command \
  "INSERT INTO agent_runs (agent_name, status, records_processed, finished_at) VALUES ('context-updater', 'success', 1, CURRENT_TIMESTAMP)"
```

## 失敗時
- CLAUDE.md を変更しない
- agent_runs に status='failure' と error_message を記録する
