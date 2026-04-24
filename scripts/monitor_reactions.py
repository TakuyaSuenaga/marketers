import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests_oauthlib import OAuth1

from scripts.data_store import load_json, append_unique

X_API_KEY       = os.environ.get("X_API_KEY", "")
X_API_SECRET    = os.environ.get("X_API_SECRET", "")
X_ACCESS_TOKEN  = os.environ.get("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET = os.environ.get("X_ACCESS_SECRET", "")

POSTED_TWEETS_PATH      = Path("data/posted_tweets.json")
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

    body = response.json()
    tweets_data = body.get("data", [])
    users_index = {
        u["id"]: u["username"]
        for u in body.get("includes", {}).get("users", [])
    }

    seen: set[str] = set()
    unique_users: list[dict] = []
    for t in tweets_data:
        author_id = t["author_id"]
        if author_id not in seen:
            seen.add(author_id)
            unique_users.append({"id": author_id, "username": users_index.get(author_id, "")})
    return unique_users


def collect_reactions(tweet: dict) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    like_candidates = [
        {
            "user_id": user["id"],
            "username": user["username"],
            "reaction_type": "like",
            "tweet_id": tweet["tweet_id"],
            "theme": tweet["theme"],
            "detected_at": now,
        }
        for user in fetch_liking_users(tweet["tweet_id"])
    ]
    reply_candidates = [
        {
            "user_id": user["id"],
            "username": user["username"],
            "reaction_type": "reply",
            "tweet_id": tweet["tweet_id"],
            "theme": tweet["theme"],
            "detected_at": now,
        }
        for user in fetch_reply_users(tweet["tweet_id"])
    ]
    return [*like_candidates, *reply_candidates]


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

        try:
            candidates = collect_reactions(tweet)
        except requests.HTTPError as e:
            print(f"  エラー (スキップ): {e}")
            continue
        prev_len = len(load_json(CUSTOMER_CANDIDATES_PATH))
        for candidate in candidates:
            candidate_with_id = {
                **candidate,
                "id": f"{candidate['user_id']}_{candidate['tweet_id']}",
            }
            result = append_unique(CUSTOMER_CANDIDATES_PATH, candidate_with_id, key="id")
            if len(result) > prev_len:
                new_candidates_count += 1
                print(f"  新規候補: @{candidate['username']} ({candidate['reaction_type']})")
                prev_len = len(result)

    print(f"\n完了: 新規顧客候補 {new_candidates_count} 件追加")
    print(f"累計: {len(load_json(CUSTOMER_CANDIDATES_PATH))} 件")


if __name__ == "__main__":
    main()
