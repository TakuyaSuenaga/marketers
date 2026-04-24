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
