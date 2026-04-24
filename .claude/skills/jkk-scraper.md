# JKKスクレイパー 実行スキル

## 概要
JKK東京（東京都住宅供給公社）の公社住宅データを収集してD1に保存する手順。

## サイト構造メモ
- エントリーURL: `https://jhomes.to-kousya.or.jp/search/jkknet/service/akiyaJyoukenStartInit`
- フォームリダイレクトあり（hidden input: `redirect`, `url`）
- JavaScript必須 → Playwright使用

## 前提条件
- wrangler d1 migrations apply kouei-db --local が完了していること
- playwright + chromium がインストール済みであること
- JKKサイト構造を事前に `agents/explore/` で確認していること

## 実行手順

### 1. サイト構造の事前確認
```bash
python agents/explore/explore_sites.py 2>&1 | grep -A 20 "JKK"
```
→ リダイレクト先URLと物件一覧の構造を確認する。

### 2. DB接続確認
```bash
cd workers
wrangler d1 execute kouei-db --local --command "SELECT COUNT(*) as count FROM properties WHERE source='jkk'"
```

### 3. スクレイパー実行
```bash
python agents/jkk-scraper/scraper.py --limit 10
```
→ まず10件でテスト。エラーがなければ全件実行：
```bash
python agents/jkk-scraper/scraper.py
```

### 4. 結果確認
```bash
cd workers
wrangler d1 execute kouei-db --local --command "SELECT agent_name, status, records_processed, finished_at FROM agent_runs WHERE agent_name='jkk-scraper' ORDER BY finished_at DESC LIMIT 5"
```

## エラー対処

### フォームリダイレクトで詰まる場合
→ `agents/explore/explore_detail.py` でJKKのリダイレクト先URLを確認する。
→ hidden inputの `url` フィールドの値を直接取得してナビゲートする。

### ログインが必要な場合
→ JKKの公開物件情報のみ対象とし、ログイン不要のページを探す。
→ `to-kousya.or.jp/chintai/reco/` の推薦物件ページを代替として検討する。

## 自己改善ルール
- JKKサイトは構造変更が多い → エラー時は必ず explore スクリプトで再確認する
- 実行頻度: 毎日1回（GitHub Actions cron: `0 6 * * *`）
