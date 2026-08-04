---
name: chinatravel-agent-env
description: Use when solving ChinaTravel benchmark queries with the local agent_env CLI, including loading benchmark queries, inspecting attractions/restaurants/hotels/transport, producing itinerary JSON, and evaluating one solved query.
---

# ChinaTravel Agent Environment

Use this skill when a task asks you to solve or inspect ChinaTravel benchmark
queries with the local `agent_env` command-line interface.

## Core Rule

Use the structured CLI tools first. Use raw `world` commands only when the
structured tool catalog does not cover the lookup.

Run commands from the repository root:

```bash
python -m agent_env.cli --lang en tools
python -m agent_env.cli --lang en splits
python -m agent_env.cli --lang en call <tool_name> '<json_arguments>'
python -m agent_env.cli --lang en world "<WorldEnv command>"
```

The CLI returns JSON. Check `success` before relying on `data`.

## Common Lookups

List query splits:

```bash
python -m agent_env.cli --lang en call china_travel_list_splits
```

Load query metadata:

```bash
python -m agent_env.cli --lang en call china_travel_load_query '{"split":"easy"}'
python -m agent_env.cli --lang en call china_travel_load_query '{"split":"easy","uid":"<uid>"}'
```

Inspect available columns:

```bash
python -m agent_env.cli --lang en call attractions_keys '{"city":"Shanghai"}'
python -m agent_env.cli --lang en call restaurants_keys '{"city":"Shanghai"}'
python -m agent_env.cli --lang en call accommodations_keys '{"city":"Shanghai"}'
```

Filter resources:

```bash
python -m agent_env.cli --lang en call attractions_select '{"city":"Shanghai","key":"name","op":"contains","value":"Museum"}'
python -m agent_env.cli --lang en call restaurants_select '{"city":"Shanghai","key":"cuisine","op":"contains","value":"Chinese"}'
python -m agent_env.cli --lang en call accommodations_select '{"city":"Shanghai","key":"price","op":"le","value":500}'
```

Find nearby resources:

```bash
python -m agent_env.cli --lang en call attractions_nearby '{"city":"Shanghai","point":"Shanghai Disneyland","topk":5,"dist":5}'
python -m agent_env.cli --lang en call restaurants_nearby '{"city":"Shanghai","point":"Shanghai Disneyland","topk":5,"dist":2}'
python -m agent_env.cli --lang en call accommodations_nearby '{"city":"Shanghai","point":"Shanghai Disneyland","topk":5,"dist":5}'
```

Check transport:

```bash
python -m agent_env.cli --lang en call intercity_transport_select '{"start_city":"Beijing","end_city":"Shanghai","intercity_type":"train","earliest_leave_time":"07:00"}'
python -m agent_env.cli --lang en call goto '{"city":"Shanghai","start":"Shanghai Railway Station","end":"Shanghai Disneyland","start_time":"09:00","transport_type":"metro"}'
```

Use the exact values returned by the tools for prices, IDs, names, times,
distances, and transport segments. Do not invent POI names or transport details.

## Output Contract

Return only a JSON itinerary matching `chinatravel/evaluation/output_schema.json`.
The top-level object must include:

- `people_number`
- `start_city`
- `target_city`
- `itinerary`

Each activity must include:

- `type`
- `start_time`
- `end_time`
- `price`
- `cost`
- `transports`

Intercity activities also need `start`, `end`, `tickets`, and `TrainID` or
`FlightID`. Attraction activities need `position` and `tickets`.
Accommodation activities need `position`, `room_type`, and `rooms`.

## Split Automation

Use the bundled harness to load a configured split, call a harness non-interactively,
save plans under `results/<method>/<uid>.json`, and evaluate them:

```bash
python agent_env/scripts/solve_script_with_harness.py --lang en --split easy
```

Useful options:

```bash
python agent_env/scripts/solve_script_with_harness.py --lang en --split easy --uid <uid>
python agent_env/scripts/solve_script_with_harness.py --lang en --split easy --harness opencode --model dashscope/qwen3.6-27b
python agent_env/scripts/solve_script_with_harness.py --lang en --split easy --harness codex --model gpt-5.5
python agent_env/scripts/solve_script_with_harness.py --lang en --split easy --timeout 900
python agent_env/scripts/solve_script_with_harness.py --lang en --split easy --limit 1
python agent_env/scripts/solve_script_with_harness.py --lang en --split easy --no-run-harness
```

The harness hides oracle verifier fields from the selected model, but keeps them
internally for hard-constraint evaluation. Result directories default to
`<model>-<split>-<harness>` unless a method override is supplied.
