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
    mock_get.return_value = mock_response([
        {"author_id": "10", "author_username": "bob"},
        {"author_id": "10", "author_username": "bob"},
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
