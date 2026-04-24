# Agent SDK リファクタリング設計

## Goal

`scripts/generate_and_post.py` からインラインのシステムプロンプトを排除し、Claude Agent SDK のサブエージェント・スキル・フックを活用してロジックを分離する。uv で依存管理し、GitHub Actions・ローカル双方で `uv run` で実行できる。

## Architecture

```
main()
  ├── select_theme()
  ├── build_options() → ClaudeAgentOptions
  │     ├── agents: { hook_writer, post_writer }
  │     ├── hooks:  { PreToolUse, PostToolUse, Stop }
  │     └── output_format: JSON Schema
  ├── query(prompt=build_prompt(theme), options=options)
  │     └── orchestrator
  │           ├── hook_writer agent (hook-generator skill)
  │           └── post_writer agent (scqa-writing-framework + structured-copywriting-skill)
  ├── parse output["post"]
  ├── post_to_x(post_text)
  └── append_unique(POSTED_TWEETS_PATH, record)
```

## Tech Stack

- Python 3.11、uv（依存管理）
- `claude-agent-sdk`（Agent SDK）
- `requests`、`requests-oauthlib`（X API）
- Claude Code CLI（`npm install -g @anthropic-ai/claude-code`、GitHub Actions で別途インストール）

## Components

### `pyproject.toml`（新規）

uv プロジェクト設定。依存パッケージ:
- `claude-agent-sdk`
- `requests`
- `requests-oauthlib`

### `scripts/generate_and_post.py`（変更）

**削除するもの:**
- `HOOK_SYSTEM_PROMPT`
- `POST_SYSTEM_PROMPT`
- `generate_hooks()` 関数
- `generate_full_post()` 関数
- `anthropic` SDK の import

**追加するもの:**

#### フック関数

| 関数名 | フックイベント | マッチャー | 処理内容 |
|--------|---------------|-----------|---------|
| `log_agent_start` | `PreToolUse` | `"Agent"` | エージェント名・開始時刻をログ出力 |
| `log_and_validate` | `PostToolUse` | `"Agent"` | エージェント名・結果をログ出力。`post_writer` の出力に対しては文字数（120〜140）・ハッシュタグ数（1〜2）を検証し、違反時は `additionalContext` で再生成を要求 |
| `log_cost` | `Stop` | なし（全対象） | セッション終了をログ出力（コストは `query()` ループ内の `ResultMessage.total_cost_usd` から別途取得） |

#### エージェント定義

```
hook_writer:
  description: "X投稿の冒頭フックを3案生成する"
  prompt:      "hook-generatorスキルに従い、20文字以内の日本語フックを3案生成してください。"
  skills:      ["hook-generator"]
  model:       "haiku"

post_writer:
  description: "フックを使ってX投稿全文をSCQA構造で生成する"
  prompt:      "scqa-writing-frameworkとstructured-copywriting-skillに従い、投稿を生成してください。"
  skills:      ["scqa-writing-framework", "structured-copywriting-skill"]
  model:       "haiku"
```

#### output_format（JSON Schema）

```json
{
  "type": "json_schema",
  "schema": {
    "type": "object",
    "properties": {
      "hooks":         { "type": "array", "items": { "type": "string" }, "minItems": 3, "maxItems": 3 },
      "selected_hook": { "type": "string" },
      "post":          { "type": "string", "minLength": 120, "maxLength": 140 }
    },
    "required": ["hooks", "selected_hook", "post"]
  }
}
```

#### build_prompt()

唯一のプロンプト文字列を持つ関数。システムプロンプトは持たない。

```
テーマ: {theme}
具体例: {example}
痛み: {pain}

hook_writer で日本語フックを3案（各20文字以内）生成し、
post_writer で最良のフックを使い120〜140文字・ハッシュタグ1〜2個のX投稿を作ってください。
```

**変更なし:**
- `THEMES` リスト
- `select_theme()`
- `post_to_x()`
- `append_unique()` による永続化ロジック

### `.github/workflows/daily_post.yml`（変更）

1. `npm install -g @anthropic-ai/claude-code` ステップを追加
2. `pip install ...` を削除
3. `python scripts/generate_and_post.py` を `uv run python scripts/generate_and_post.py` に変更

### スキルファイル（変更なし）

`.claude/skills/` 以下の SKILL.md は変更しない。

## Data Flow

```
select_theme()
  → build_prompt(theme)         # テーマデータ + 制約のみ
  → query(prompt, options)
      → hook_writer              # hook-generator skill が冒頭フックを3案生成
      → post_writer              # scqa + structured-copywriting skills が全文生成
      → log_and_validate hook    # 120〜140文字 / ハッシュタグ 1〜2個を検証
  → ResultMessage.total_cost_usd をログ出力
  → output: { hooks, selected_hook, post }  # JSON Schema 保証済み
  → post_to_x(post)
  → append_unique(record)
```

## Error Handling

- フォーマット違反: `log_and_validate` フックが `additionalContext` でリトライを要求。Agent SDK が Claude に再生成を促す。
- X API エラー: 既存の `raise_for_status()` がそのまま動作し、GitHub Actions ログに出力される。
- CLI 未インストール: `CLINotFoundError` が上がる。GitHub Actions のワークフローで `npm install` が先行するため通常は発生しない。

## Testing

- 既存テスト（`tests/test_data_store.py`、`tests/test_monitor_reactions.py`）はそのまま動作する。
- `generate_and_post.py` のテストは Agent SDK の `query()` をモックして追加する。
