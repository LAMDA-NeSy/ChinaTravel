# ChinaTravel Agent Environment

[English](README.md) | [简体中文](README.zh-CN.md)

This directory wraps the existing ChinaTravel environment for agent runtimes without
modifying the benchmark package. Official running and evaluation scripts such as
`run_exp.py`, `eval_exp.py`, and `eval_tpc.py` remain the source of truth.

## What This Provides

- `agent_env.adapter.ChinaTravelEnvAdapter`: Python API that lazily loads the official
  `WorldEnv` and returns JSON-serializable results.
- `agent_env.cli`: dependency-free command-line interface for one-shot calls and
  interactive terminal use.
- `agent_env.mcp_stdio`: dependency-free stdio MCP-style bridge for agent clients.
- `agent_env.http_server`: dependency-free local HTTP JSON service for other agents or
  scripts.
- `agent_env/SKILL.md`: agent instructions for using the CLI to solve benchmark
  queries.
- `agent_env/scripts/solve_script_with_harness.py`: split harness that loads queries,
  calls OpenCode or Codex, saves plans, and evaluates them.

## Prerequisites

Install the project requirements and download the current official sandbox from
[Hugging Face](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel-Sandbox):

```bash
pip install -r requirements.txt
# install database/ and database_en/ under chinatravel/environment/
```

Legacy sandbox snapshots are unsupported. The runtime uses entity names and
concept labels exactly as stored in the installed sandbox.

The wrapper itself can start without those dependencies, but environment tool calls will
return initialization errors until the official prerequisites are present.

## Agent/MCP-Style Usage

Configure the agent client to run:

```bash
CHINATRAVEL_LANG=en python -m agent_env.mcp_stdio
```

`CHINATRAVEL_LANG` selects both the query language and sandbox database. It accepts
`en` or `zh`.

The server exposes tools such as:

- `attractions_keys`
- `attractions_select`
- `restaurants_nearby`
- `goto`
- `intercity_transport_select`
- `poi_lat_lon_search`
- `china_travel_load_query`
- `china_travel_world_command`

Prefer the structured tools first. Use `china_travel_world_command` only when an
advanced query needs the original `WorldEnv` command-string surface.

## CLI Usage

List available tools:

```bash
python -m agent_env.cli --lang en tools
```

Call a structured tool:

```bash
python -m agent_env.cli --lang en call attractions_keys '{"city":"Shanghai"}'
```

Call the original command-string interface:

```bash
python -m agent_env.cli --lang en world "attractions_keys('Shanghai')"
```

Start an interactive prompt:

```bash
python -m agent_env.cli --lang en
```

Inside the prompt:

```text
tools
splits
call attractions_nearby {"city":"上海","point":"上海迪士尼度假区","topk":5,"dist":5}
world attractions_keys('上海')
quit
```

## Split Harness

Create a local config from the tracked example:

```bash
cp agent_env/config.toml.example agent_env/config.toml
```

Edit `agent_env/config.toml` to set the split, language, harness, smoke-test limit,
models, providers, and API key or API key env var. The local config is ignored
by git because it may contain a secret.

Keep `lang = "en"` for English data. This setting is applied to
query loading, environment tools, and both commonsense and hard-logic evaluation.

Important `[run]` fields are:

| Field | Meaning |
| --- | --- |
| `split` | Local split to process |
| `lang` | `en` or `zh` |
| `harness` | `opencode` or `codex` |
| `method` | Result directory name; generated when empty |
| `work_dir` | Working directory exposed to the harness |
| `tool_python` | Python command used for environment tools |
| `uid` | Run one query only |
| `limit` | Smoke-test size; `0` means no limit |
| `resume` | Skip result JSON files that already exist |
| `no_run_harness` | Parse existing output without launching an agent |
| `plan_file` | Evaluate a specified plan file |

Run the configured harness non-interactively. The config's `limit` value
controls whether this is a smoke test or a full split run:

```bash
python agent_env/scripts/solve_script_with_harness.py
```

Use a specific query or override the configured model from the CLI:

```bash
python agent_env/scripts/solve_script_with_harness.py --lang en --uid <uid>
python agent_env/scripts/solve_script_with_harness.py --harness opencode --model dashscope/qwen3.6-27b
python agent_env/scripts/solve_script_with_harness.py --harness codex --model gpt-5.5
python agent_env/scripts/solve_script_with_harness.py --resume
```

Unless `--method` or `[run].method` is set, result directories use
`<model>-<split>-<harness>`, for example
`qwen3.6-27b-generated_5000-opencode`.

Set `resume = true` under `[run]` in `agent_env/config.toml` to skip queries
that already have `results/<method>/<uid>.json`. Parse failures are saved as
all-false one-query evaluations, and the run reports the parse failure count at
the end.

The harness writes:

- prompt and raw harness logs under `agent_env/runs/<method>/<split>_<uid>/`
- the itinerary under `results/<method>/<uid>.json`
- the one-query evaluation under `agent_env/runs/<method>/<split>_<uid>/evaluation.json`
- the split summary under `agent_env/runs/<method>/<split>_summary.json`

It loads oracle fields internally for judging, but removes them from the query shown to
the selected harness. OpenCode runs write a per-run `opencode.json`, capture
JSONL events, and extract final text into `output.txt`; Codex runs use
`--output-last-message` to write `output.txt` directly.

## HTTP Usage

Start the local server:

```bash
python -m agent_env.http_server --lang en --host 127.0.0.1 --port 8765
```

List tools:

```bash
curl http://127.0.0.1:8765/tools
```

Call a tool:

```bash
curl -X POST http://127.0.0.1:8765/call \
  -H 'Content-Type: application/json' \
  -d '{"tool":"attractions_keys","arguments":{"city":"Shanghai"}}'
```

Call the original command-string interface:

```bash
curl -X POST http://127.0.0.1:8765/world-command \
  -H 'Content-Type: application/json' \
  -d '{"command":"attractions_keys(\"Shanghai\")"}'
```

## Boundary

This wrapper is for environment access and information lookup. It does not replace the
official agent execution or evaluation pipeline. Use the original scripts for benchmark
runs and scoring.
