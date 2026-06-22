# ChinaTravel Agent Environment

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
- OpenAI tool-call schema export and execution helpers for Chat Completions
  `tool_calls` and Responses API `function_call` items.
- `agent_env/SKILL.md`: agent instructions for using the CLI to solve benchmark
  queries.
- `agent_env.scripts.solve_script_with_harness`: split harness that loads queries,
  calls OpenCode or Codex, saves plans, and evaluates them.

## Prerequisites

Install the original project requirements and download the official database as usual:

```bash
pip install -r requirements.txt
# unzip the database to chinatravel/environment/database/
```

The wrapper itself can start without those dependencies, but environment tool calls will
return initialization errors until the official prerequisites are present.

## Language

The environment defaults to Chinese data. Pass `--lang en` or set
`CHINATRAVEL_ENV_LANG=en` to use the English query/environment data when it is
available. City and POI names in tool arguments must match the selected language.

## Agent/MCP-Style Usage

Configure the agent client to run:

```bash
python -m agent_env.mcp_stdio
# or
python -m agent_env.mcp_stdio --lang en
```

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
advanced query needs the restricted `WorldEnv` command-string surface.
Structured tools call `WorldEnv` component APIs directly and are the stable
interface for MCP, HTTP, and OpenAI tool calls.

Structured tools validate required arguments, unknown fields, primitive JSON
types, numeric minimums, and enum values before calling `WorldEnv`. The same
validation path is shared by the CLI, HTTP server, MCP bridge, and OpenAI
tool-call helpers.

Set `CHINATRAVEL_OPENAI_STRICT_TOOLS=1` before listing OpenAI tools if the
client should receive OpenAI strict function schemas. Leave it unset for the
broadest compatibility with OpenAI-compatible providers.

## CLI Usage

Run a lightweight protocol self-check:

```bash
python -m agent_env check
python -m agent_env --lang en check
```

List available tools:

```bash
python -m agent_env.cli tools
```

List tools in standard Chat Completions tool-call format:

```bash
python -m agent_env.cli openai-tools
```

List tools in OpenAI Responses API format:

```bash
python -m agent_env.cli responses-tools
```

Call a structured tool:

```bash
python -m agent_env.cli call attractions_keys '{"city":"上海"}'
python -m agent_env.cli --lang en call attractions_keys '{"city":"Shanghai"}'
```

For nearby-search tools, `topk` and `dist` have defaults and can be omitted:

```bash
python -m agent_env.cli call attractions_nearby '{"city":"上海","point":"上海迪士尼度假区"}'
```

Execute an OpenAI tool call object:

```bash
python -m agent_env.cli openai-call '{"id":"call_1","type":"function","function":{"name":"attractions_keys","arguments":"{\"city\":\"上海\"}"}}'
python -m agent_env.cli openai-calls '[{"id":"call_1","type":"function","function":{"name":"china_travel_list_splits","arguments":"{}"}}]'
```

Return standard OpenAI `role=tool` response messages:

```bash
python -m agent_env.cli openai-message '{"id":"call_1","type":"function","function":{"name":"attractions_keys","arguments":"{\"city\":\"上海\"}"}}'
python -m agent_env.cli openai-messages '[{"id":"call_1","type":"function","function":{"name":"china_travel_list_splits","arguments":"{}"}}]'
```

Return OpenAI Responses API `function_call_output` items:

```bash
python -m agent_env.cli responses-output '{"type":"function_call","call_id":"call_1","name":"china_travel_list_splits","arguments":"{}"}'
python -m agent_env.cli responses-outputs '[{"type":"function_call","call_id":"call_1","name":"china_travel_list_splits","arguments":"{}"}]'
```

Call the original command-string interface:

```bash
python -m agent_env.cli world "attractions_keys('上海')"
```

Start an interactive prompt:

```bash
python -m agent_env
```

Inside the prompt:

```text
check
tools
openai-tools
responses-tools
splits
call attractions_nearby {"city":"上海","point":"上海迪士尼度假区","topk":5,"dist":5}
openai-call {"id":"call_1","type":"function","function":{"name":"attractions_keys","arguments":"{\"city\":\"上海\"}"}}
openai-calls [{"id":"call_1","type":"function","function":{"name":"china_travel_list_splits","arguments":"{}"}}]
openai-message {"id":"call_1","type":"function","function":{"name":"attractions_keys","arguments":"{\"city\":\"上海\"}"}}
openai-messages [{"id":"call_1","type":"function","function":{"name":"china_travel_list_splits","arguments":"{}"}}]
responses-output {"type":"function_call","call_id":"call_1","name":"china_travel_list_splits","arguments":"{}"}
responses-outputs [{"type":"function_call","call_id":"call_1","name":"china_travel_list_splits","arguments":"{}"}]
world attractions_keys('上海')
quit
```

## Split Harness

Create a local config from the tracked example:

```bash
cp agent_env/config.toml.example agent_env/config.toml
```

Edit `agent_env/config.toml` to set the split, harness, smoke-test limit,
models, providers, and API key or API key env var. The local config is ignored
by git because it may contain a secret.

Run the configured harness non-interactively over the configured split and
evaluate each output:

```bash
python -m agent_env.scripts.solve_script_with_harness
```

Smoke test the configured split with the config's `limit` value:

```bash
python -m agent_env.scripts.solve_script_with_harness
```

Use a specific query or override the configured model from the CLI:

```bash
python -m agent_env.scripts.solve_script_with_harness --uid <uid>
python -m agent_env.scripts.solve_script_with_harness --harness opencode --model openai/gpt-5.5
python -m agent_env.scripts.solve_script_with_harness --harness codex --model gpt-5.5
python -m agent_env.scripts.solve_script_with_harness --resume
```

Unless `--method` or `[run].method` is set, result directories use
`<model>-<split>-<harness>`, for example
`gpt-5.5-easy-opencode`.

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
python -m agent_env.http_server --host 127.0.0.1 --port 8765
python -m agent_env.http_server --host 127.0.0.1 --port 8765 --lang en
```

The HTTP server returns JSON, supports CORS headers, and handles `OPTIONS`
preflight requests for local browser or agent integrations.

List tools:

```bash
curl http://127.0.0.1:8765/tools
```

Run the same protocol self-check over HTTP:

```bash
curl http://127.0.0.1:8765/self-check
```

List tools in Chat Completions format:

```bash
curl http://127.0.0.1:8765/openai-tools
```

List tools in Responses API format:

```bash
curl http://127.0.0.1:8765/responses-tools
```

Call a tool:

```bash
curl -X POST http://127.0.0.1:8765/call \
  -H 'Content-Type: application/json' \
  -d '{"tool":"attractions_keys","arguments":{"city":"上海"}}'
```

Execute an OpenAI tool call object:

```bash
curl -X POST http://127.0.0.1:8765/openai-tool-call \
  -H 'Content-Type: application/json' \
  -d '{"id":"call_1","type":"function","function":{"name":"attractions_keys","arguments":"{\"city\":\"上海\"}"}}'
```

Execute multiple OpenAI tool calls or receive ready-to-append `role=tool`
messages:

```bash
curl -X POST http://127.0.0.1:8765/openai-tool-messages \
  -H 'Content-Type: application/json' \
  -d '{"tool_calls":[{"id":"call_1","type":"function","function":{"name":"attractions_keys","arguments":"{\"city\":\"上海\"}"}}]}'
```

Return Responses API `function_call_output` items:

```bash
curl -X POST http://127.0.0.1:8765/responses-tool-outputs \
  -H 'Content-Type: application/json' \
  -d '{"tool_calls":[{"type":"function_call","call_id":"call_1","name":"china_travel_list_splits","arguments":"{}"}]}'
```

Call the original command-string interface:

```bash
curl -X POST http://127.0.0.1:8765/world-command \
  -H 'Content-Type: application/json' \
  -d '{"command":"attractions_keys(\"上海\")"}'
```

## Boundary

This wrapper is for environment access and information lookup. It does not replace the
official agent execution or evaluation pipeline. Use the original scripts for benchmark
runs and scoring.
