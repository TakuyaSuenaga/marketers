# URスクレイパー 実行スキル

## 概要
UR賃貸住宅（東京都）の物件データを収集してD1に保存する手順。

## 前提条件
- wrangler d1 migrations apply kouei-db --local が完了していること
- playwright + chromium がインストール済みであること

## 実行手順

### 1. DB接続確認
```bash
cd workers
wrangler d1 execute kouei-db --local --command "SELECT COUNT(*) as count FROM properties WHERE source='ur'"
```
→ 現在のUR物件数を確認する。

### 2. スクレイパー実行
```bash
python agents/ur-scraper/scraper.py --limit 10
```
→ まず10件でテスト。エラーがなければ全件実行：
```bash
python agents/ur-scraper/scraper.py
```

### 3. 結果確認
```bash
cd workers
wrangler d1 execute kouei-db --local --command "SELECT COUNT(*) as count, source FROM properties GROUP BY source"
wrangler d1 execute kouei-db --local --command "SELECT agent_name, status, records_processed, finished_at FROM agent_runs ORDER BY finished_at DESC LIMIT 5"
```

### 4. データサンプル確認
```bash
cd workers
wrangler d1 execute kouei-db --local --command "SELECT name, city, rent_yen, floor_plan, nearest_station FROM properties WHERE source='ur' LIMIT 5"
```

## エラー対処

### "D1データベースが見つかりません"
→ `cd workers && wrangler d1 migrations apply kouei-db --local` を実行する。

### タイムアウトエラー
→ `--limit 5` で少量から試す。ネットワーク状況を確認する。

### パースエラーが多い場合
→ `agents/explore/explore_detail.py` を実行してサイト構造の変化を確認する。
→ `agents/ur-scraper/scraper.py` のセレクタを修正してスキルファイルを更新する。

## 自己改善ルール
- 失敗パターンを発見したら、このスキルファイルの「エラー対処」に追記する
- パースロジックを修正したら、修正内容と理由をコメントに残す
- 実行頻度: 毎時1回（GitHub Actions cron: `0 * * * *`）
