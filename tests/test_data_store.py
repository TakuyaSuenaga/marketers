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
