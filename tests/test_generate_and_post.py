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
    # 140文字・ハッシュタグ2個: "a"*129 + " #自動化 #業務改善" = 129+1+4+1+5 = 140
    post = "a" * 129 + " #自動化 #業務改善"
    assert len(post) == 140
    result = await log_and_validate(
        make_post_input("post_writer", {"result": post}), None, {}
    )
    assert result == {}


async def test_log_and_validate_blocks_too_short_post():
    short_post = "短い #自動化"
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
    no_tag = "a" * 125
    result = await log_and_validate(
        make_post_input("post_writer", {"result": no_tag}), None, {}
    )
    assert "additionalContext" in result.get("hookSpecificOutput", {})


async def test_log_and_validate_blocks_three_hashtags():
    three_tags = "a" * 100 + " #a #b #c"
    result = await log_and_validate(
        make_post_input("post_writer", {"result": three_tags}), None, {}
    )
    assert "additionalContext" in result.get("hookSpecificOutput", {})


async def test_log_and_validate_skips_hook_writer():
    result = await log_and_validate(
        make_post_input("hook_writer", {"result": "短い"}), None, {}
    )
    assert result == {}


# ── log_cost ─────────────────────────────────────────────────

async def test_log_cost_returns_empty_dict(capsys):
    result = await log_cost(make_stop_input(), None, {})
    captured = capsys.readouterr()
    assert result == {}
    assert "COST" in captured.out or captured.out == ""
