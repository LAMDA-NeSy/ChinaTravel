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
python -m agent_env.cli tools
python -m agent_env.cli openai-tools
python -m agent_env.cli responses-tools
python -m agent_env.cli splits
python -m agent_env.cli call <tool_name> '<json_arguments>'
python -m agent_env.cli world "<WorldEnv command>"
```

The CLI returns JSON. Check `success` before relying on `data`.

## Common Lookups

List query splits:

```bash
python -m agent_env.cli call china_travel_list_splits
```

Load query metadata:

```bash
python -m agent_env.cli call china_travel_load_query '{"split":"easy"}'
python -m agent_env.cli call china_travel_load_query '{"split":"easy","uid":"<uid>"}'
```

Inspect available columns:

```bash
python -m agent_env.cli call attractions_keys '{"city":"上海"}'
python -m agent_env.cli call restaurants_keys '{"city":"上海"}'
python -m agent_env.cli call accommodations_keys '{"city":"上海"}'
```

Filter resources:

```bash
python -m agent_env.cli call attractions_select '{"city":"上海","key":"name","op":"contains","value":"博物馆"}'
python -m agent_env.cli call restaurants_select '{"city":"上海","key":"cuisine","op":"eq","value":"本帮江浙菜"}'
python -m agent_env.cli call accommodations_select '{"city":"上海","key":"price","op":"le","value":500}'
```

Find nearby resources:

```bash
python -m agent_env.cli call attractions_nearby '{"city":"上海","point":"上海迪士尼度假区","topk":5,"dist":5}'
python -m agent_env.cli call restaurants_nearby '{"city":"上海","point":"上海迪士尼度假区","topk":5,"dist":2}'
python -m agent_env.cli call accommodations_nearby '{"city":"上海","point":"上海迪士尼度假区","topk":5,"dist":5}'
```

Check transport:

```bash
python -m agent_env.cli call intercity_transport_select '{"start_city":"北京","end_city":"上海","intercity_type":"train","earliest_leave_time":"07:00"}'
python -m agent_env.cli call goto '{"city":"上海","start":"上海站","end":"上海迪士尼度假区","start_time":"09:00","transport_type":"metro"}'
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
python -m agent_env.scripts.solve_script_with_harness --split easy
```

Useful options:

```bash
python -m agent_env.scripts.solve_script_with_harness --split easy --uid <uid>
python -m agent_env.scripts.solve_script_with_harness --split easy --harness opencode --model openai/gpt-5.5
python -m agent_env.scripts.solve_script_with_harness --split easy --harness codex --model gpt-5.5
python -m agent_env.scripts.solve_script_with_harness --split easy --timeout 900
python -m agent_env.scripts.solve_script_with_harness --split easy --limit 1
python -m agent_env.scripts.solve_script_with_harness --split easy --no-run-harness
```

The harness hides oracle verifier fields from the selected model, but keeps them
internally for hard-constraint evaluation. Result directories default to
`<model>-<split>-<harness>` unless a method override is supplied.
