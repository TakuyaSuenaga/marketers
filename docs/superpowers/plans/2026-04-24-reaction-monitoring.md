# Reaction Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 毎日の自動投稿で反応（いいね・リプライ）したユーザーを自動収集し、顧客候補リストとして蓄積する。

**Architecture:** 既存の投稿スクリプトを拡張してツイートIDを `data/posted_tweets.json` に永続化する。別スクリプト `monitor_reactions.py` が X API v2 でいいね・リプライを取得し、新規ユーザーを `data/customer_candidates.json` に追記する。どちらも GitHub Actions から実行し、更新されたデータファイルをリポジトリへコミットする。

**Tech Stack:** Python 3.11, pytest, requests, requests-oauthlib, X API v2 (Basic tier 以上推奨), GitHub Actions

---

## 現状のコードベース

```
scripts/generate_and_post.py   # Claude でネタ生成 → X に投稿（2ステップ）
.github/workflows/daily_post.yml  # GitHub Actions（cronコメントアウト中）
```

---

## 追加・変更ファイル一覧

| パス | 種別 | 責務 |
|------|------|------|
| `data/posted_tweets.json` | 新規（データ） | 投稿済みツイートID・テーマ・日時を永続化 |
| `data/customer_candidates.json` | 新規（データ） | 反応ユーザーの一覧（重複なし） |
| `scripts/generate_and_post.py` | 変更 | 投稿後にツイートIDをデータファイルへ書き込む |
| `scripts/monitor_reactions.py` | 新規 | いいね・リプライユーザーを取得してCSVに追記 |
| `scripts/data_store.py` | 新規 | JSONファイル読み書きのユーティリティ（副作用を分離） |
| `tests/test_data_store.py` | 新規 | data_store のユニットテスト |
| `tests/test_monitor_reactions.py` | 新規 | monitor_reactions のユニットテスト |
| `.github/workflows/daily_post.yml` | 変更 | 投稿後にデータファイルを git commit |
| `.github/workflows/monitor_reactions.yml` | 新規 | 1日1回反応を監視して git commit |

---

## Task 1: データ永続化ユーティリティを TDD で作る

**Files:**
- Create: `scripts/data_store.py`
- Create: `tests/test_data_store.py`

- [ ] **Step 1: pytest をセットアップする**

```bash
pip install pytest
```

- [ ] **Step 2: テストファイルを作成する**

`tests/test_data_store.py` を以下の内容で作成：

```python
import json
import pytest
from pathlib import Path
from scripts.data_store import load_json, save_json, append_unique


@pytest.fixture
def tmp_json(tmp_path):
    return tmp_path / "data.json"


def test_load_json_returns_empty_list_when_file_missing(tmp_json):
    result = load_json(tmp_json)
    assert result == []


def test_save_and_load_roundtrip(tmp_json):
    data = [{"id": "1", "theme": "test"}]
    save_json(tmp_json, data)
    assert load_json(tmp_json) == data


def test_append_unique_adds_new_item(tmp_json):
    save_json(tmp_json, [{"id": "1"}])
    result = append_unique(tmp_json, {"id": "2"}, key="id")
    assert len(result) == 2


def test_append_unique_skips_duplicate(tmp_json):
    save_json(tmp_json, [{"id": "1"}])
    result = append_unique(tmp_json, {"id": "1"}, key="id")
    assert len(result) == 1


def test_append_unique_creates_file_if_missing(tmp_json):
    result = append_unique(tmp_json, {"id": "99"}, key="id")
    assert result == [{"id": "99"}]
    assert tmp_json.exists()
```

- [ ] **Step 3: テストが失敗することを確認する**

```bash
cd /path/to/marketers
python -m pytest tests/test_data_store.py -v
```

期待: `ModuleNotFoundError: No module named 'scripts.data_store'`

- [ ] **Step 4: `scripts/data_store.py` を実装する**

```python
import json
from pathlib import Path


def load_json(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_unique(path: Path, item: dict, key: str) -> list:
    records = load_json(path)
    existing_keys = {r[key] for r in records}
    if item[key] not in existing_keys:
        records.append(item)
        save_json(path, records)
    return records
```

- [ ] **Step 5: `scripts/__init__.py` を作成する（importのため）**

```bash
touch scripts/__init__.py
touch tests/__init__.py
```

- [ ] **Step 6: テストが全てパスすることを確認する**

```bash
python -m pytest tests/test_data_store.py -v
```

期待:
```
PASSED tests/test_data_store.py::test_load_json_returns_empty_list_when_file_missing
PASSED tests/test_data_store.py::test_save_and_load_roundtrip
PASSED tests/test_data_store.py::test_append_unique_adds_new_item
PASSED tests/test_data_store.py::test_append_unique_skips_duplicate
PASSED tests/test_data_store.py::test_append_unique_creates_file_if_missing
5 passed
```

- [ ] **Step 7: コミットする**

```bash
git add scripts/__init__.py scripts/data_store.py tests/__init__.py tests/test_data_store.py
git commit -m "feat: add JSON data store utility with unique-append"
```

---

## Task 2: 投稿スクリプトにツイートID永続化を追加する

**Files:**
- Modify: `scripts/generate_and_post.py:129-159`（main関数）
- Modify: `data/posted_tweets.json`（実行時に自動生成）

- [ ] **Step 1: `data/` ディレクトリを作成し `.gitkeep` を置く**

```bash
mkdir -p data
touch data/.gitkeep
```

- [ ] **Step 2: `generate_and_post.py` の import と定数を更新する**

ファイル冒頭の import ブロックに追加：

```python
from pathlib import Path
from scripts.data_store import append_unique

POSTED_TWEETS_PATH = Path("data/posted_tweets.json")
```

- [ ] **Step 3: `main()` に保存ロジックを追加する**

`main()` 内の「# 5. 結果をJSONで出力」ブロックの直後（`print(json.dumps(...))` の後）に追記：

```python
    # 6. ツイートIDをデータファイルへ永続化
    from datetime import datetime, timezone
    record = {
        "tweet_id": tweet_id,
        "theme": theme["theme"],
        "post": post_text,
        "hooks": hooks,
        "posted_at": datetime.now(timezone.utc).isoformat(),
    }
    append_unique(POSTED_TWEETS_PATH, record, key="tweet_id")
    print(f"ツイートID保存完了: {POSTED_TWEETS_PATH}")
```

- [ ] **Step 4: ローカルでドライラン（X投稿なしで動作確認）**

環境変数に仮の値を設定して `main()` の投稿直前で止めるか、以下でインポートだけ確認：

```bash
python -c "from scripts.generate_and_post import select_theme, generate_hooks; print('import OK')"
```

期待: `import OK`

- [ ] **Step 5: コミットする**

```bash
git add data/.gitkeep scripts/generate_and_post.py
git commit -m "feat: persist tweet ID to data/posted_tweets.json after posting"
```

---

## Task 3: 反応監視スクリプトを TDD で作る

**Files:**
- Create: `scripts/monitor_reactions.py`
- Create: `tests/test_monitor_reactions.py`

- [ ] **Step 1: テストファイルを作成する**

`tests/test_monitor_reactions.py` を以下の内容で作成：

```python
import pytest
from unittest.mock import patch, MagicMock
from scripts.monitor_reactions import (
    fetch_liking_users,
    fetch_reply_users,
    collect_reactions,
)


def make_user(user_id: str, username: str) -> dict:
    return {"id": user_id, "username": username}


def mock_response(data: list) -> MagicMock:
    m = MagicMock()
    m.json.return_value = {"data": data}
    m.raise_for_status.return_value = None
    return m


@patch("scripts.monitor_reactions.requests.get")
def test_fetch_liking_users_returns_users(mock_get):
    mock_get.return_value = mock_response([make_user("1", "alice")])
    users = fetch_liking_users("tweet123")
    assert users == [{"id": "1", "username": "alice"}]
    mock_get.assert_called_once()


@patch("scripts.monitor_reactions.requests.get")
def test_fetch_liking_users_returns_empty_on_no_data(mock_get):
    m = MagicMock()
    m.json.return_value = {}  # "data" キーなし
    m.raise_for_status.return_value = None
    mock_get.return_value = m
    assert fetch_liking_users("tweet123") == []


@patch("scripts.monitor_reactions.requests.get")
def test_fetch_reply_users_returns_unique_authors(mock_get):
    mock_get.return_value = mock_response([
        {"author_id": "10", "author_username": "bob"},
        {"author_id": "10", "author_username": "bob"},  # 重複
        {"author_id": "20", "author_username": "carol"},
    ])
    users = fetch_reply_users("tweet123")
    assert len(users) == 2
    assert {"id": "10", "username": "bob"} in users


def test_collect_reactions_merges_likes_and_replies():
    tweet = {"tweet_id": "t1", "theme": "会計事務所の月次処理"}
    with patch("scripts.monitor_reactions.fetch_liking_users") as fl, \
         patch("scripts.monitor_reactions.fetch_reply_users") as fr:
        fl.return_value = [{"id": "1", "username": "alice"}]
        fr.return_value = [{"id": "2", "username": "bob"}]
        candidates = collect_reactions(tweet)
    assert len(candidates) == 2
    assert candidates[0]["reaction_type"] == "like"
    assert candidates[1]["reaction_type"] == "reply"
    assert candidates[0]["tweet_id"] == "t1"
    assert candidates[0]["theme"] == "会計事務所の月次処理"
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
python -m pytest tests/test_monitor_reactions.py -v
```

期待: `ModuleNotFoundError: No module named 'scripts.monitor_reactions'`

- [ ] **Step 3: `scripts/monitor_reactions.py` を実装する**

```python
import os
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests_oauthlib import OAuth1

from scripts.data_store import load_json, append_unique

X_API_KEY      = os.environ["X_API_KEY"]
X_API_SECRET   = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET = os.environ["X_ACCESS_SECRET"]

POSTED_TWEETS_PATH     = Path("data/posted_tweets.json")
CUSTOMER_CANDIDATES_PATH = Path("data/customer_candidates.json")

X_BASE_URL = "https://api.twitter.com/2"


def _auth() -> OAuth1:
    return OAuth1(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)


def fetch_liking_users(tweet_id: str) -> list[dict]:
    url = f"{X_BASE_URL}/tweets/{tweet_id}/liking_users"
    response = requests.get(url, auth=_auth())
    response.raise_for_status()
    return response.json().get("data", [])


def fetch_reply_users(tweet_id: str) -> list[dict]:
    url = f"{X_BASE_URL}/tweets/search/recent"
    params = {
        "query": f"conversation_id:{tweet_id}",
        "tweet.fields": "author_id",
        "expansions": "author_id",
        "user.fields": "username",
    }
    response = requests.get(url, auth=_auth(), params=params)
    response.raise_for_status()

    raw_users = response.json().get("data", [])
    seen = set()
    unique_users = []
    for u in raw_users:
        if u["author_id"] not in seen:
            seen.add(u["author_id"])
            unique_users.append({"id": u["author_id"], "username": u.get("author_username", "")})
    return unique_users


def collect_reactions(tweet: dict) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    candidates = []

    for user in fetch_liking_users(tweet["tweet_id"]):
        candidates.append({
            "user_id": user["id"],
            "username": user["username"],
            "reaction_type": "like",
            "tweet_id": tweet["tweet_id"],
            "theme": tweet["theme"],
            "detected_at": now,
        })

    for user in fetch_reply_users(tweet["tweet_id"]):
        candidates.append({
            "user_id": user["id"],
            "username": user["username"],
            "reaction_type": "reply",
            "tweet_id": tweet["tweet_id"],
            "theme": tweet["theme"],
            "detected_at": now,
        })

    return candidates


def main():
    print("=== 反応監視エージェント 起動 ===")

    tweets = load_json(POSTED_TWEETS_PATH)
    if not tweets:
        print("監視対象のツイートがありません。")
        return

    new_candidates_count = 0
    for tweet in tweets:
        tweet_id = tweet["tweet_id"]
        print(f"監視中: {tweet_id} ({tweet['theme']})")

        candidates = collect_reactions(tweet)
        for candidate in candidates:
            # user_id + tweet_id の組み合わせをキーにして重複排除
            candidate["id"] = f"{candidate['user_id']}_{candidate['tweet_id']}"
            before = len(load_json(CUSTOMER_CANDIDATES_PATH))
            append_unique(CUSTOMER_CANDIDATES_PATH, candidate, key="id")
            after = len(load_json(CUSTOMER_CANDIDATES_PATH))
            if after > before:
                new_candidates_count += 1
                print(f"  新規候補: @{candidate['username']} ({candidate['reaction_type']})")

    print(f"\n完了: 新規顧客候補 {new_candidates_count} 件追加")
    print(f"累計: {len(load_json(CUSTOMER_CANDIDATES_PATH))} 件")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストが全てパスすることを確認する**

```bash
python -m pytest tests/test_monitor_reactions.py -v
```

期待:
```
PASSED tests/test_monitor_reactions.py::test_fetch_liking_users_returns_users
PASSED tests/test_monitor_reactions.py::test_fetch_liking_users_returns_empty_on_no_data
PASSED tests/test_monitor_reactions.py::test_fetch_reply_users_returns_unique_authors
PASSED tests/test_monitor_reactions.py::test_collect_reactions_merges_likes_and_replies
4 passed
```

- [ ] **Step 5: コミットする**

```bash
git add scripts/monitor_reactions.py tests/test_monitor_reactions.py
git commit -m "feat: add reaction monitoring script with like and reply collection"
```

---

## Task 4: GitHub Actions を更新する

**Files:**
- Modify: `.github/workflows/daily_post.yml`
- Create: `.github/workflows/monitor_reactions.yml`

- [ ] **Step 1: `daily_post.yml` にデータファイルのコミットステップを追加する**

`.github/workflows/daily_post.yml` の最後のステップ（`python scripts/generate_and_post.py` の後）に追記：

```yaml
      - name: 投稿データをコミット
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/posted_tweets.json || true
          git diff --staged --quiet || git commit -m "chore: record posted tweet $(date +%Y-%m-%d)"
          git push
```

また、cronのコメントアウトを外す（毎朝8時JST = UTC 23時）：

```yaml
on:
  schedule:
    - cron: "0 23 * * *"
  workflow_dispatch:
```

- [ ] **Step 2: `monitor_reactions.yml` を新規作成する**

`.github/workflows/monitor_reactions.yml` を以下の内容で作成：

```yaml
name: 反応監視エージェント

on:
  schedule:
    # 毎日9時（JST）= UTC 0時 に実行（投稿の1時間後）
    - cron: "0 0 * * *"
  workflow_dispatch:

jobs:
  monitor:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: リポジトリをチェックアウト
        uses: actions/checkout@v4

      - name: Python セットアップ
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: 依存パッケージをインストール
        run: |
          pip install requests requests-oauthlib

      - name: 反応を監視
        env:
          X_API_KEY:      ${{ secrets.X_API_KEY }}
          X_API_SECRET:   ${{ secrets.X_API_SECRET }}
          X_ACCESS_TOKEN: ${{ secrets.X_ACCESS_TOKEN }}
          X_ACCESS_SECRET: ${{ secrets.X_ACCESS_SECRET }}
        run: |
          python scripts/monitor_reactions.py

      - name: 顧客候補データをコミット
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/customer_candidates.json || true
          git diff --staged --quiet || git commit -m "chore: update customer candidates $(date +%Y-%m-%d)"
          git push
```

- [ ] **Step 3: ワークフロー設定を確認する**

```bash
python -m pytest tests/ -v
```

期待: 全テストパス（既存のテストも含む）

- [ ] **Step 4: コミットする**

```bash
git add .github/workflows/daily_post.yml .github/workflows/monitor_reactions.yml
git commit -m "feat: wire GitHub Actions for auto-commit and reaction monitoring workflow"
```

---

## 完成後のフロー

```
毎朝8時 daily_post.yml
  → ネタ生成（2ステップ）
  → X投稿
  → data/posted_tweets.json に保存してコミット

毎朝9時 monitor_reactions.yml
  → posted_tweets.json を読み込む
  → 各ツイートのいいね・リプライを取得
  → data/customer_candidates.json に追記してコミット
```

---

## X API 利用上の注意

- いいね取得（`/liking_users`）・リプライ検索（`/search/recent`）は **Basic ティア ($100/月) 以上** を推奨
- Free ティアの場合は月500リクエストの上限があり、複数ツイートの監視で枯渇する可能性あり
- `response.raise_for_status()` が `429` を返す場合は rate limit 超過。GitHub Actions のログで確認できる
