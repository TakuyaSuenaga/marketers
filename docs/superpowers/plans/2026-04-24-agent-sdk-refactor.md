# Agent SDK リファクタリング実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `generate_and_post.py` のインラインプロンプトを排除し、Claude Agent SDK のサブエージェント・スキル・フックで再実装する。uv で依存管理し、GitHub Actions・ローカル双方で動作する。

**Architecture:** `query()` に最小プロンプト（テーマデータのみ）を渡す。`hook_writer`（hook-generator スキル）と `post_writer`（scqa + structured-copywriting スキル）の 2 サブエージェントが生成を担当。フックでロギングとフォーマット検証を行う。

**Tech Stack:** Python 3.11、uv、claude-agent-sdk、requests、requests-oauthlib、pytest、pytest-asyncio

---

## ファイル一覧

| パス | 種別 | 責務 |
|------|------|------|
| `pyproject.toml` | 新規 | uv プロジェクト設定・依存管理 |
| `uv.lock` | 新規（自動生成） | 依存ロックファイル |
| `scripts/generate_and_post.py` | 全面書き直し | Agent SDK でコンテンツ生成・投稿・永続化 |
| `tests/test_generate_and_post.py` | 新規 | フック関数・build_prompt・run_generation のテスト |
| `.github/workflows/daily_post.yml` | 変更 | Node.js + uv セットアップ、uv run に切り替え |

---

## Task 1: uv プロジェクトをセットアップする

**Files:**
- Create: `pyproject.toml`
- Create: `uv.lock`（コマンド実行で自動生成）

- [ ] **Step 1: 作業ディレクトリを確認する**

```bash
cd /Users/suenagatakuya/Documents/develop/marketers
ls pyproject.toml 2>/dev/null || echo "not found"
```

期待: `not found`

- [ ] **Step 2: uv で pyproject.toml を初期化する**

```bash
uv init --no-readme --no-pin-python
```

期待: `pyproject.toml` と `uv.lock` が生成される。`hello.py` が生成されたら削除する。

```bash
rm -f hello.py
```

- [ ] **Step 3: 本番依存パッケージを追加する**

```bash
uv add claude-agent-sdk requests requests-oauthlib
```

期待: `pyproject.toml` の `dependencies` に 3 つが追加される。

- [ ] **Step 4: 開発用依存パッケージを追加する**

```bash
uv add --dev pytest pytest-asyncio
```

- [ ] **Step 5: pyproject.toml に pytest 設定を追加する**

`pyproject.toml` の末尾に以下を追記する（`[build-system]` セクションの後）:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 6: import が通ることを確認する**

```bash
uv run python -c "from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition, HookMatcher; print('OK')"
```

期待: `OK`

- [ ] **Step 7: コミットする**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add uv project with claude-agent-sdk dependencies"
```

---

## Task 2: フック関数を TDD で実装する

**Files:**
- Modify: `scripts/generate_and_post.py`（フック関数 3 つを末尾に追加）
- Create: `tests/test_generate_and_post.py`

- [ ] **Step 1: テストファイルを作成する**

`tests/test_generate_and_post.py` を以下の内容で作成する:

```python
import pytest
from scripts.generate_and_post import log_agent_start, log_and_validate, log_cost


def make_pre_input(subagent_type: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {"subagent_type": subagent_type, "prompt": "test", "description": "test"},
        "tool_use_id": "tid",
        "session_id": "sid",
        "transcript_path": "/tmp/t",
        "cwd": "/tmp",
    }


def make_post_input(subagent_type: str, result: str | dict) -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Agent",
        "tool_input": {"subagent_type": subagent_type, "prompt": "test", "description": "test"},
        "tool_response": result,
        "tool_use_id": "tid",
        "session_id": "sid",
        "transcript_path": "/tmp/t",
        "cwd": "/tmp",
    }


def make_stop_input() -> dict:
    return {
        "hook_event_name": "Stop",
        "stop_hook_active": False,
        "session_id": "sid",
        "transcript_path": "/tmp/t",
        "cwd": "/tmp",
    }


# ── log_agent_start ──────────────────────────────────────────

async def test_log_agent_start_logs_agent_name(capsys):
    result = await log_agent_start(make_pre_input("hook_writer"), None, {})
    captured = capsys.readouterr()
    assert "hook_writer" in captured.out
    assert result == {}


async def test_log_agent_start_returns_empty_dict():
    result = await log_agent_start(make_pre_input("post_writer"), None, {})
    assert result == {}


# ── log_and_validate ─────────────────────────────────────────

async def test_log_and_validate_passes_valid_post():
    # 120文字ちょうど・ハッシュタグ1個
    valid_post = "a" * 115 + " #自動化"  # 115 + 1 + 4 = 120
    result = await log_and_validate(
        make_post_input("post_writer", {"result": valid_post}), None, {}
    )
    assert result == {}


async def test_log_and_validate_passes_140_char_post():
    # 140文字・ハッシュタグ2個
    post = "a" * 124 + " #自動化 #業務改善"  # 124+1+4+1+5 = 135... let me count carefully
    # "#自動化" = 4 chars, "#業務改善" = 6 chars, spaces = 2 chars → 4+6+2 = 12
    # 140 - 12 = 128 "a"s
    post = "a" * 128 + " #自動化 #業務改善"
    assert len(post) == 140
    result = await log_and_validate(
        make_post_input("post_writer", {"result": post}), None, {}
    )
    assert result == {}


async def test_log_and_validate_blocks_too_short_post():
    short_post = "短い #自動化"  # 7 chars < 120
    result = await log_and_validate(
        make_post_input("post_writer", {"result": short_post}), None, {}
    )
    specific = result.get("hookSpecificOutput", {})
    assert specific.get("hookEventName") == "PostToolUse"
    assert "additionalContext" in specific


async def test_log_and_validate_blocks_too_long_post():
    long_post = "a" * 136 + " #自動化"  # 136+1+4 = 141 chars
    assert len(long_post) == 141
    result = await log_and_validate(
        make_post_input("post_writer", {"result": long_post}), None, {}
    )
    assert "additionalContext" in result.get("hookSpecificOutput", {})


async def test_log_and_validate_blocks_no_hashtag():
    no_tag = "a" * 125  # 125 chars, no hashtag
    result = await log_and_validate(
        make_post_input("post_writer", {"result": no_tag}), None, {}
    )
    assert "additionalContext" in result.get("hookSpecificOutput", {})


async def test_log_and_validate_blocks_three_hashtags():
    three_tags = "a" * 100 + " #a #b #c"  # 109 chars, 3 hashtags
    result = await log_and_validate(
        make_post_input("post_writer", {"result": three_tags}), None, {}
    )
    assert "additionalContext" in result.get("hookSpecificOutput", {})


async def test_log_and_validate_skips_hook_writer():
    # hook_writer の出力はバリデーション対象外
    result = await log_and_validate(
        make_post_input("hook_writer", {"result": "短い"}), None, {}
    )
    assert result == {}


# ── log_cost ─────────────────────────────────────────────────

async def test_log_cost_returns_empty_dict(capsys):
    result = await log_cost(make_stop_input(), None, {})
    captured = capsys.readouterr()
    assert result == {}
    assert "COST" in captured.out or captured.out == ""  # ログ出力またはno-op
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
uv run pytest tests/test_generate_and_post.py -v 2>&1 | head -20
```

期待: `ImportError: cannot import name 'log_agent_start'`

- [ ] **Step 3: `scripts/generate_and_post.py` の末尾にフック関数を追加する**

既存ファイルの末尾（`if __name__ == "__main__":` の前）に以下を追記する:

```python
# ── フック関数 ────────────────────────────────────────────────
from typing import Any


async def log_agent_start(
    input_data: dict[str, Any], tool_use_id: str | None, context: dict
) -> dict[str, Any]:
    agent = input_data["tool_input"].get("subagent_type", "unknown")
    print(f"[AGENT START] {agent} ({datetime.now().isoformat()})")
    return {}


async def log_and_validate(
    input_data: dict[str, Any], tool_use_id: str | None, context: dict
) -> dict[str, Any]:
    agent = input_data["tool_input"].get("subagent_type", "unknown")
    response = input_data.get("tool_response", {})
    result_text = response.get("result", str(response)) if isinstance(response, dict) else str(response)
    print(f"[AGENT END] {agent}: {result_text[:80]}")

    if agent != "post_writer":
        return {}

    char_count = len(result_text)
    hashtag_count = result_text.count("#")
    if 120 <= char_count <= 140 and 1 <= hashtag_count <= 2:
        return {}

    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"投稿が条件を満たしていません（{char_count}文字、ハッシュタグ{hashtag_count}個）。"
                "120〜140文字、ハッシュタグ1〜2個で再生成してください。"
            ),
        }
    }


async def log_cost(
    input_data: dict[str, Any], tool_use_id: str | None, context: dict
) -> dict[str, Any]:
    print("[COST] セッション終了")
    return {}
```

- [ ] **Step 4: テストが全てパスすることを確認する**

```bash
uv run pytest tests/test_generate_and_post.py -v
```

期待:
```
PASSED tests/test_generate_and_post.py::test_log_agent_start_logs_agent_name
PASSED tests/test_generate_and_post.py::test_log_agent_start_returns_empty_dict
PASSED tests/test_generate_and_post.py::test_log_and_validate_passes_valid_post
PASSED tests/test_generate_and_post.py::test_log_and_validate_passes_140_char_post
PASSED tests/test_generate_and_post.py::test_log_and_validate_blocks_too_short_post
PASSED tests/test_generate_and_post.py::test_log_and_validate_blocks_too_long_post
PASSED tests/test_generate_and_post.py::test_log_and_validate_blocks_no_hashtag
PASSED tests/test_generate_and_post.py::test_log_and_validate_blocks_three_hashtags
PASSED tests/test_generate_and_post.py::test_log_and_validate_skips_hook_writer
PASSED tests/test_generate_and_post.py::test_log_cost_returns_empty_dict
10 passed
```

- [ ] **Step 5: コミットする**

```bash
git add scripts/generate_and_post.py tests/test_generate_and_post.py
git commit -m "feat: add hook functions for agent logging and post validation"
```

---

## Task 3: generate_and_post.py を Agent SDK に全面移行する

**Files:**
- Modify: `scripts/generate_and_post.py`（全面書き直し）
- Modify: `tests/test_generate_and_post.py`（build_prompt・run_generation のテスト追加）

- [ ] **Step 1: `tests/test_generate_and_post.py` に新しいテストを追記する**

ファイル末尾に以下を追記する:

```python
# ── build_prompt ─────────────────────────────────────────────
from scripts.generate_and_post import build_prompt


def test_build_prompt_contains_theme_data():
    theme = {"theme": "会計事務所", "example": "freee入力", "pain": "繰り返し作業"}
    prompt = build_prompt(theme)
    assert "会計事務所" in prompt
    assert "freee入力" in prompt
    assert "繰り返し作業" in prompt


def test_build_prompt_mentions_both_agents():
    theme = {"theme": "t", "example": "e", "pain": "p"}
    prompt = build_prompt(theme)
    assert "hook_writer" in prompt
    assert "post_writer" in prompt


# ── run_generation ────────────────────────────────────────────
from scripts.generate_and_post import run_generation
from unittest.mock import patch
from claude_agent_sdk import ResultMessage


async def test_run_generation_returns_structured_output():
    theme = {"theme": "テスト", "example": "例", "pain": "痛み"}
    mock_result = ResultMessage(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=900,
        is_error=False,
        num_turns=2,
        session_id="test-session",
        total_cost_usd=0.001,
        structured_output={
            "hooks": ["h1", "h2", "h3"],
            "selected_hook": "h1",
            "post": "a" * 115 + " #自動化",
        },
    )

    async def fake_query(**kwargs):
        yield mock_result

    with patch("scripts.generate_and_post.query", new=fake_query):
        output = await run_generation(theme)

    assert output["post"] == "a" * 115 + " #自動化"
    assert output["hooks"] == ["h1", "h2", "h3"]
    assert output["selected_hook"] == "h1"


async def test_run_generation_raises_on_no_output():
    theme = {"theme": "テスト", "example": "例", "pain": "痛み"}
    from claude_agent_sdk import AssistantMessage, TextBlock

    # structured_output が None の ResultMessage
    mock_result = ResultMessage(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=900,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        structured_output=None,
    )

    async def fake_query(**kwargs):
        yield mock_result

    with patch("scripts.generate_and_post.query", new=fake_query):
        with pytest.raises(ValueError, match="生成結果が取得できませんでした"):
            await run_generation(theme)
```

- [ ] **Step 2: テストが失敗することを確認する**

```bash
uv run pytest tests/test_generate_and_post.py::test_build_prompt_contains_theme_data -v
```

期待: `ImportError: cannot import name 'build_prompt'`

- [ ] **Step 3: `scripts/generate_and_post.py` を全面書き直す**

ファイル全体を以下の内容に置き換える:

```python
import os
import json
import random
import asyncio
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from requests_oauthlib import OAuth1
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    HookMatcher,
    ResultMessage,
)
from scripts.data_store import append_unique

X_API_KEY       = os.environ["X_API_KEY"]
X_API_SECRET    = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN  = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET = os.environ["X_ACCESS_SECRET"]

X_POST_URL = "https://api.twitter.com/2/tweets"
POSTED_TWEETS_PATH = Path("data/posted_tweets.json")

THEMES = [
    {
        "theme": "会計事務所の月次処理",
        "example": "freeeへの領収書入力を毎月100件手作業でやっている",
        "pain": "同じ操作を何十回も繰り返す単純作業",
    },
    {
        "theme": "不動産会社の物件登録",
        "example": "SUUMOとathomeに同じ物件情報を二重入力している",
        "pain": "複数サイトへの転記作業で1件あたり30分かかる",
    },
    {
        "theme": "歯科医院の予約管理",
        "example": "電話予約を紙の台帳とシステム両方に記入している",
        "pain": "二重管理でミスが起きやすい",
    },
    {
        "theme": "法律事務所の書類作成",
        "example": "契約書の定型部分を毎回コピペして修正している",
        "pain": "テンプレートから手修正する作業に1時間かかる",
    },
    {
        "theme": "美容院の顧客管理",
        "example": "施術記録をカルテに手書きしてからシステムに入力している",
        "pain": "二度手間で閉店後の事務作業が毎日30分以上かかる",
    },
    {
        "theme": "個人病院の会計処理",
        "example": "レセプトと会計システムのデータ照合を手作業でやっている",
        "pain": "月末の締め作業が丸一日かかる",
    },
]

OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "hooks": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
            "selected_hook": {"type": "string"},
            "post": {"type": "string", "minLength": 120, "maxLength": 140},
        },
        "required": ["hooks", "selected_hook", "post"],
    },
}


# ── フック関数 ────────────────────────────────────────────────

async def log_agent_start(
    input_data: dict[str, Any], tool_use_id: str | None, context: dict
) -> dict[str, Any]:
    agent = input_data["tool_input"].get("subagent_type", "unknown")
    print(f"[AGENT START] {agent} ({datetime.now().isoformat()})")
    return {}


async def log_and_validate(
    input_data: dict[str, Any], tool_use_id: str | None, context: dict
) -> dict[str, Any]:
    agent = input_data["tool_input"].get("subagent_type", "unknown")
    response = input_data.get("tool_response", {})
    result_text = (
        response.get("result", str(response)) if isinstance(response, dict) else str(response)
    )
    print(f"[AGENT END] {agent}: {result_text[:80]}")

    if agent != "post_writer":
        return {}

    char_count = len(result_text)
    hashtag_count = result_text.count("#")
    if 120 <= char_count <= 140 and 1 <= hashtag_count <= 2:
        return {}

    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"投稿が条件を満たしていません（{char_count}文字、ハッシュタグ{hashtag_count}個）。"
                "120〜140文字、ハッシュタグ1〜2個で再生成してください。"
            ),
        }
    }


async def log_cost(
    input_data: dict[str, Any], tool_use_id: str | None, context: dict
) -> dict[str, Any]:
    print("[COST] セッション終了")
    return {}


# ── Agent SDK 設定 ───────────────────────────────────────────

def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        agents={
            "hook_writer": AgentDefinition(
                description="X投稿の冒頭フックを3案生成する",
                prompt="hook-generatorスキルに従い、20文字以内の日本語フックを3案生成してください。",
                skills=["hook-generator"],
                model="haiku",
            ),
            "post_writer": AgentDefinition(
                description="フックを使ってX投稿全文をSCQA構造で生成する",
                prompt="scqa-writing-frameworkとstructured-copywriting-skillに従い、投稿を生成してください。",
                skills=["scqa-writing-framework", "structured-copywriting-skill"],
                model="haiku",
            ),
        },
        hooks={
            "PreToolUse":  [HookMatcher(matcher="Agent", hooks=[log_agent_start])],
            "PostToolUse": [HookMatcher(matcher="Agent", hooks=[log_and_validate])],
            "Stop":        [HookMatcher(hooks=[log_cost])],
        },
        output_format=OUTPUT_SCHEMA,
    )


def build_prompt(theme: dict) -> str:
    return (
        f"テーマ: {theme['theme']}\n"
        f"具体例: {theme['example']}\n"
        f"痛み: {theme['pain']}\n\n"
        "hook_writer で日本語フックを3案（各20文字以内）生成し、"
        "post_writer で最良のフックを使い120〜140文字・ハッシュタグ1〜2個のX投稿を作ってください。"
    )


async def run_generation(theme: dict) -> dict[str, Any]:
    options = build_options()
    prompt = build_prompt(theme)
    output = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            if message.total_cost_usd is not None:
                print(f"[COST] Total: ${message.total_cost_usd:.4f} USD")
            if message.structured_output:
                output = message.structured_output

    if output is None:
        raise ValueError("生成結果が取得できませんでした")

    return output


# ── X API ────────────────────────────────────────────────────

def post_to_x(text: str) -> dict:
    auth = OAuth1(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)
    response = requests.post(
        X_POST_URL,
        auth=auth,
        json={"text": text},
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    return response.json()


def select_theme() -> dict:
    return random.choice(THEMES)


# ── エントリポイント ──────────────────────────────────────────

async def main():
    print("=== X投稿エージェント 起動 ===")

    theme = select_theme()
    print(f"テーマ: {theme['theme']}")

    print("\nコンテンツ生成中（Agent SDK）...")
    output = await run_generation(theme)

    print("\nフック候補:")
    for i, hook in enumerate(output["hooks"], 1):
        print(f"  [{i}] {hook}")
    print(f"\n採用フック: {output['selected_hook']}")
    print(f"\n生成された投稿文:\n{output['post']}")
    print(f"文字数: {len(output['post'])}")

    print("\nXに投稿中...")
    result = post_to_x(output["post"])
    tweet_id = result.get("data", {}).get("id", "unknown")
    print(f"投稿完了: https://twitter.com/i/web/status/{tweet_id}")

    record = {
        "tweet_id": tweet_id,
        "theme": theme["theme"],
        "post": output["post"],
        "hooks": output["hooks"],
        "posted_at": datetime.now(timezone.utc).isoformat(),
    }
    append_unique(POSTED_TWEETS_PATH, record, key="tweet_id")
    print(f"ツイートID保存完了: {POSTED_TWEETS_PATH}")

    print(json.dumps({
        "theme": theme["theme"],
        "hooks": output["hooks"],
        "selected_hook": output["selected_hook"],
        "post": output["post"],
        "tweet_id": tweet_id,
        "char_count": len(output["post"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: 全テストがパスすることを確認する**

```bash
uv run pytest tests/ -v
```

期待:
```
PASSED tests/test_data_store.py::test_load_json_returns_empty_list_when_file_missing
PASSED tests/test_data_store.py::test_save_and_load_roundtrip
PASSED tests/test_data_store.py::test_append_unique_adds_new_item
PASSED tests/test_data_store.py::test_append_unique_skips_duplicate
PASSED tests/test_data_store.py::test_append_unique_creates_file_if_missing
PASSED tests/test_monitor_reactions.py::... (6 tests)
PASSED tests/test_generate_and_post.py::... (14 tests)
25 passed
```

- [ ] **Step 5: コミットする**

```bash
git add scripts/generate_and_post.py tests/test_generate_and_post.py
git commit -m "feat: migrate generate_and_post.py to Agent SDK with subagents and hooks"
```

---

## Task 4: GitHub Actions を uv + Claude Code CLI 対応に更新する

**Files:**
- Modify: `.github/workflows/daily_post.yml`

- [ ] **Step 1: `.github/workflows/daily_post.yml` を以下の内容に書き直す**

```yaml
name: 毎日X投稿エージェント

on:
  # schedule:
  #   - cron: "0 23 * * *"
  workflow_dispatch:
    # 手動実行ボタンも有効にする（テスト用）

jobs:
  post:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: リポジトリをチェックアウト
        uses: actions/checkout@v4

      - name: Node.js セットアップ
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Claude Code CLI をインストール
        run: npm install -g @anthropic-ai/claude-code

      - name: uv セットアップ
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"

      - name: 依存パッケージをインストール
        run: uv sync

      - name: X に投稿
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          X_API_KEY:         ${{ secrets.X_API_KEY }}
          X_API_SECRET:      ${{ secrets.X_API_SECRET }}
          X_ACCESS_TOKEN:    ${{ secrets.X_ACCESS_TOKEN }}
          X_ACCESS_SECRET:   ${{ secrets.X_ACCESS_SECRET }}
        run: |
          uv run python scripts/generate_and_post.py

      - name: 投稿データをコミット
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/posted_tweets.json || true
          git diff --staged --quiet || git commit -m "chore: record posted tweet $(date +%Y-%m-%d)"
          git push
```

- [ ] **Step 2: YAML の構文を確認する**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/daily_post.yml')); print('YAML OK')"
```

期待: `YAML OK`

- [ ] **Step 3: 全テストが引き続きパスすることを確認する**

```bash
uv run pytest tests/ -v --tb=short
```

期待: `25 passed`

- [ ] **Step 4: コミットする**

```bash
git add .github/workflows/daily_post.yml
git commit -m "chore: update daily_post workflow to use uv and Claude Code CLI"
```
