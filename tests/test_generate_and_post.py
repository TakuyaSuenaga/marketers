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
