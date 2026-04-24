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
