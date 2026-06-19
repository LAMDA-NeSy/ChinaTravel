# Synthetic Query Generation

This folder contains an experimental pipeline for generating harder ChinaTravel
queries from already valid seed plans.

The core idea is:

1. Sample unconstrained trip requests.
2. Run a planner, for example UrbanTrip, to obtain feasible seed plans.
3. Sample strict DSL constraints from each seed plan.
4. Render the sampled constraints into templated natural language.
5. Verify that the original seed plan satisfies every generated constraint.
6. Optionally polish the natural language later with an LLM while preserving the
   exact constraint semantics.

The generated records follow the regular query JSON structure:

- `uid`
- `start_city`
- `target_city`
- `days`
- `people_number`
- `hard_logic_py`
- `hard_logic_nl`
- `nature_language`

Additional trace fields are included so generated data can be audited:

- `source_plan_uid`
- `seed_plan_path`
- `generation_profile`

## Generate Seed Queries

Use this to create simple trip requests with only origin, destination, number of
travelers, and trip duration. These are meant to be solved by UrbanTrip or
another planner before constraint sampling.

```bash
python synthetic_query_generation/generate_synthetic_queries.py seed-queries \
  --output-dir /tmp/chinatravel_seed_queries \
  --num-records 100 \
  --lang en \
  --seed 2026
```

After generating seed queries, run a planner on that folder and collect the
resulting plan JSON files.

## Generate Harder Queries From Plans

Use `from-plans` on a directory of valid plan JSON files:

```bash
python synthetic_query_generation/generate_synthetic_queries.py from-plans \
  --plans-dir results/UrbanTrip_TPCLLM_en_oracletranslation \
  --output-dir /tmp/chinatravel_synthetic_hard \
  --num-records 100 \
  --lang en \
  --seed 2026 \
  --copy-seed-plans
```

The script samples constraints from each plan, validates every candidate with
`evaluate_constraints_py`, and validates the final selected constraint set
again before writing a record. If a candidate fails verification on the seed
plan, it is discarded.

The output layout is:

```text
<output-dir>/
  data/
    <uid>.json
  seed_plans/             # only when --copy-seed-plans is used
    <uid>.json
  manifest.json
```

`manifest.json` includes:

- generation counts
- skipped seed plans
- constraint template catalog
- concrete rendered template examples

## Constraint Families

The current sampler can generate:

- basic trip constraints: days, traveler count, ticket count
- exact attraction, restaurant, and hotel names
- attraction, restaurant, and hotel feature/type sets
- room count and room type constraints
- in-city transportation mode constraints
- taxi car-count constraints
- intercity transportation mode constraints
- day-specific POI constraints
- time-window constraints
- attraction ordering constraints
- tight budget constraints for total, food, hotel, attraction, and in-city transport costs

The default profile favors constraints that are often harder for UrbanTrip:
exact names, time windows, ordering, tight budgets, day-specific requirements,
and combined type sets.

## Languages

Both English and Chinese templates are supported:

```bash
--lang en
--lang zh
--lang auto
```

`auto` infers the language from the seed plan city names. Entity names are kept
exactly as they appear in the seed plan.

## Polishing Stub

The polishing step is intentionally separated. The current stub does not call an
LLM; it prepares strict prompts or copies records unchanged.

Generate polishing prompts:

```bash
python synthetic_query_generation/polish_queries_stub.py \
  --input-dir /tmp/chinatravel_synthetic_hard/data \
  --output-dir /tmp/chinatravel_polish_prompts \
  --mode prompts
```

Copy records without polishing:

```bash
python synthetic_query_generation/polish_queries_stub.py \
  --input-dir /tmp/chinatravel_synthetic_hard/data \
  --output-dir /tmp/chinatravel_unpolished_copy \
  --mode copy
```

Any future LLM polishing implementation should use `hard_logic_nl` as a
constraint checklist and must not add, remove, weaken, or strengthen
requirements.
