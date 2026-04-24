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
    m.json.return_value = {}
    m.raise_for_status.return_value = None
    mock_get.return_value = m
    assert fetch_liking_users("tweet123") == []


@patch("scripts.monitor_reactions.requests.get")
def test_fetch_reply_users_returns_unique_authors(mock_get):
    m = MagicMock()
    m.json.return_value = {
        "data": [
            {"author_id": "10"},
            {"author_id": "10"},  # 重複
            {"author_id": "20"},
        ],
        "includes": {
            "users": [
                {"id": "10", "username": "bob"},
                {"id": "20", "username": "carol"},
            ]
        },
    }
    m.raise_for_status.return_value = None
    mock_get.return_value = m
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


def test_main_exits_early_when_no_tweets(tmp_path, capsys):
    from scripts.monitor_reactions import main
    import scripts.monitor_reactions as mod
    original = mod.POSTED_TWEETS_PATH
    mod.POSTED_TWEETS_PATH = tmp_path / "posted_tweets.json"
    try:
        main()
        captured = capsys.readouterr()
        assert "監視対象のツイートがありません" in captured.out
    finally:
        mod.POSTED_TWEETS_PATH = original


def test_main_adds_new_candidates(tmp_path, capsys):
    from scripts.data_store import save_json
    from scripts.monitor_reactions import main
    import scripts.monitor_reactions as mod

    posted_path = tmp_path / "posted_tweets.json"
    candidates_path = tmp_path / "customer_candidates.json"
    save_json(posted_path, [{"tweet_id": "t1", "theme": "テスト"}])

    original_posted = mod.POSTED_TWEETS_PATH
    original_candidates = mod.CUSTOMER_CANDIDATES_PATH
    mod.POSTED_TWEETS_PATH = posted_path
    mod.CUSTOMER_CANDIDATES_PATH = candidates_path

    try:
        with patch("scripts.monitor_reactions.collect_reactions") as mock_collect:
            mock_collect.return_value = [
                {"user_id": "1", "username": "alice", "reaction_type": "like",
                 "tweet_id": "t1", "theme": "テスト", "detected_at": "2026-01-01T00:00:00+00:00"}
            ]
            main()
        from scripts.data_store import load_json
        candidates = load_json(candidates_path)
        assert len(candidates) == 1
        assert candidates[0]["username"] == "alice"
    finally:
        mod.POSTED_TWEETS_PATH = original_posted
        mod.CUSTOMER_CANDIDATES_PATH = original_candidates
