import os
import json
import random
import requests
from datetime import datetime, timezone
from pathlib import Path
from anthropic import Anthropic
from requests_oauthlib import OAuth1
from scripts.data_store import append_unique

POSTED_TWEETS_PATH = Path("data/posted_tweets.json")

# ── 設定 ────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
X_API_KEY         = os.environ["X_API_KEY"]
X_API_SECRET      = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN    = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET   = os.environ["X_ACCESS_SECRET"]

X_POST_URL = "https://api.twitter.com/2/tweets"

# ── 投稿テーマのローテーション ────────────────────────────
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

# ── プロンプト ────────────────────────────────────────────
HOOK_SYSTEM_PROMPT = """
あなたはSNSマーケターです。中小企業・士業・医療機関向けのX投稿の冒頭フックを生成します。

## フックの条件
- 20文字以内
- 読んだ瞬間に「あ、うちのこと」と思わせる
- 以下のいずれかの手法を使う:
  - 共感できる痛み（「毎月〇時間、同じ作業してませんか？」）
  - 驚きの数字・コスト（「月20時間、消えてます」）
  - 直接的な問いかけ（「その転記、まだ手でやってる？」）

## 出力形式
フックを3つ、エンゲージメント推定が高い順でJSON配列のみ出力。
["フック1", "フック2", "フック3"]
前置き・説明は一切不要。
"""

POST_SYSTEM_PROMPT = """
あなたはAIエージェント自動化サービスのマーケターです。
中小企業・士業・医療機関の「パソコン操作の繰り返し作業」を
AIエージェントで自動化するサービスの認知を広めるためにXに投稿します。

## 投稿のルール
- 文字数: 120〜140文字（Xの上限280文字の半分以下に収める）
- 1投稿1メッセージ。複数ツイートのスレッドは作らない
- 難しい技術用語を使わない（「AIエージェント」「自動化」は使ってよい）
- 読んだ人が「うちの会社もこれあるかも」と思わせる具体性
- 最後に問いかけか行動喚起を入れる
- ハッシュタグは1〜2個まで

## フォーマット（SCQA構造）
S（状況）: 読者が共感できる日常の一コマ
C（問題）: その作業の非効率・コスト
Q/A（解決）: AIエージェントで解決できると示唆

## 出力形式
投稿文のみ。説明・前置き・コードブロック不要。
"""


def generate_hooks(theme_data: dict) -> list[str]:
    """テーマから3つのフック候補をエンゲージメント推定順で生成する"""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=HOOK_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"テーマ: {theme_data['theme']}\n"
                f"具体例: {theme_data['example']}\n"
                f"痛み: {theme_data['pain']}"
            ),
        }],
    )

    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # JSON解析失敗時は最初の行をフックとして扱う
        return [raw.split("\n")[0]]


def generate_full_post(theme_data: dict, hook: str) -> str:
    """フックを冒頭に固定してSCQA構造の全文を生成する"""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=POST_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"以下のフックを冒頭に使い、X投稿を1件生成してください。\n\n"
                f"フック（冒頭固定）: {hook}\n"
                f"テーマ: {theme_data['theme']}\n"
                f"具体例: {theme_data['example']}\n"
                f"痛み: {theme_data['pain']}\n\n"
                f"SCQA構造で120〜140文字（フック含む）、ハッシュタグ1〜2個で書いてください。"
            ),
        }],
    )

    return message.content[0].text.strip()


def post_to_x(text: str) -> dict:
    """X API v2で投稿する"""
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


def main():
    print("=== X投稿エージェント 起動 ===")

    # 1. テーマ選択
    theme = select_theme()
    print(f"テーマ: {theme['theme']}")

    # 2. フック生成（3案）
    print("\nフック候補を生成中...")
    hooks = generate_hooks(theme)
    for i, hook in enumerate(hooks, 1):
        print(f"  [{i}] {hook}")

    best_hook = hooks[0]
    print(f"\n採用フック: {best_hook}")

    # 3. フックをベースに全文生成
    print("\n投稿文を生成中...")
    post_text = generate_full_post(theme, best_hook)
    print(f"\n生成された投稿文:\n{post_text}\n")
    print(f"文字数: {len(post_text)}")

    # 4. X API で投稿
    print("Xに投稿中...")
    result = post_to_x(post_text)
    tweet_id = result.get("data", {}).get("id", "unknown")
    print(f"投稿完了: https://twitter.com/i/web/status/{tweet_id}")

    # 5. 結果をJSONで出力（GitHub Actionsのログ確認用）
    output = {
        "theme": theme["theme"],
        "hooks": hooks,
        "selected_hook": best_hook,
        "post": post_text,
        "tweet_id": tweet_id,
        "char_count": len(post_text),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    # 6. ツイートIDをデータファイルへ永続化
    record = {
        "tweet_id": tweet_id,
        "theme": theme["theme"],
        "post": post_text,
        "hooks": hooks,
        "posted_at": datetime.now(timezone.utc).isoformat(),
    }
    append_unique(POSTED_TWEETS_PATH, record, key="tweet_id")
    print(f"ツイートID保存完了: {POSTED_TWEETS_PATH}")


if __name__ == "__main__":
    main()
