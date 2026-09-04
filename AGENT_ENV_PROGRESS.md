# Agent Environment Progress

## 2026-05-21

- Confirmed the existing benchmark already exposes `WorldEnv` plus domain APIs under
  `chinatravel/environment/tools`.
- Kept ChinaTravel source files unchanged.
- Added an external `agent_env/` wrapper with lazy initialization so the wrapper can
  start even before the full benchmark runtime is installed.
- Added structured JSON tools for attractions, accommodations, restaurants, POI lookup,
  city transportation, intercity transportation, split listing, and query loading.
- Added a dependency-free stdio MCP-style bridge for agent clients:
  `python -m agent_env.mcp_stdio`.
- Added a dependency-free local HTTP service:
  `python -m agent_env.http_server --host 127.0.0.1 --port 8765`.
- Confirmed the official database is present under `chinatravel/environment/database`.
- Verified real environment calls with a temporary uv dependency environment:
  `attractions_keys('上海')` and an `attractions_nearby` table query both succeed.
- The default `python` in this shell is 3.14 and lacks project dependencies. Use the
  README's Python 3.9 environment, or a temporary `uv run --with ...` environment, for
  real tool calls.

## Next Useful Checks

- Run a real tool call after dependencies and database are present.
- Point the target agent client at `python -m agent_env.mcp_stdio`.
- Keep benchmark evaluation on `eval_exp.py` / `eval_tpc.py`.

## 2026-05-27

- Added a dependency-free CLI wrapper:
  `python -m agent_env.cli`.
- The CLI supports one-shot commands for tool listing, split listing, structured tool
  calls, and raw `WorldEnv` commands.
- The CLI also supports an interactive prompt for terminal-driven agents:
  `tools`, `splits`, `call <tool> <json_arguments>`, `world <command>`, and `quit`.

## 2026-05-28

- Added `agent_env/SKILL.md` with agent-oriented instructions for solving
  ChinaTravel queries through the local CLI.
- Added `agent_env.scripts.solve_script_with_harness`, an agent harness that:
  loads a query with oracle verifier fields for judging, hides oracle fields from
  the model prompt, calls the model non-interactively, saves the resulting plan
  under `results/<method>/<uid>.json`, and evaluates schema, commonsense, and hard
  constraints with the official evaluation functions.
- Updated the harness so nested runs use per-query run directories, keeping
  generated metadata out of the repository root.
