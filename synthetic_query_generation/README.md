# Synthetic Query Generation

[English](README.md) | [简体中文](README.zh-CN.md)

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

All command examples are run from the repository root and write to the
repository-relative `artifacts/` directory, which is ignored by Git. The CLI
accepts any other relative or absolute location supplied explicitly by the
caller; no machine-specific output path is built into the generator.

## Module Layout

The generator is split into small modules so future constraints can be added or
disabled without touching the CLI or output pipeline:

- `__main__.py`: module entrypoint for `python -m synthetic_query_generation`
- `cli.py`: argument parsing and CLI validation
- `pipeline.py`: public generation APIs and output/manifest writing
- `models.py`: config dataclasses and shared candidate models
- `templates.py`: template catalog, labels, and shared tag constants
- `catalog.py`: template semantics and full/legacy/familiar release profiles
- `constraints.py`: registered constraint generator families and sampling logic
- `validation.py`: hard-constraint and commonsense validation wrappers
- `audit.py`: independent dataset, DSL, seed-plan, and coverage checks
- `export_release.py`: query-only release export
- `release_wording.py`: idempotent post-competition wording clarifications
- `utils.py`: JSON, language, formatting, plan traversal, and cost helpers

The main Python APIs are:

```python
from pathlib import Path
from synthetic_query_generation import FromPlansConfig, generate_from_plans

manifest = generate_from_plans(
    FromPlansConfig(
        plans_dir=Path("results/UrbanTrip_deepseek_en_oracletranslation"),
        output_dir=Path("artifacts/synthetic/generated"),
        num_records=100,
        lang="en",
    )
)
```

## Generate Seed Queries

Use this to create simple trip requests with only origin, destination, number of
travelers, and trip duration. These are meant to be solved by UrbanTrip or
another planner before constraint sampling.

```bash
python -m synthetic_query_generation seed-queries \
  --output-dir artifacts/synthetic/seed_queries \
  --num-records 100 \
  --lang en \
  --seed 2026
```

After generating seed queries, run a planner on that folder and collect the
resulting plan JSON files.

## Generate Harder Queries From Plans

Use `from-plans` on a directory of valid plan JSON files:

```bash
python -m synthetic_query_generation from-plans \
  --plans-dir results/UrbanTrip_deepseek_en_oracletranslation \
  --output-dir artifacts/synthetic/generated \
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

You can inspect and control generator families from the CLI:

```bash
python -m synthetic_query_generation list-generators

python -m synthetic_query_generation from-plans \
  --plans-dir results/UrbanTrip_deepseek_en_oracletranslation \
  --output-dir artifacts/synthetic/budget_only \
  --num-records 20 \
  --lang en \
  --only-generators budget,transport \
  --no-or-constraints

python -m synthetic_query_generation from-plans \
  --plans-dir results/UrbanTrip_deepseek_en_oracletranslation \
  --output-dir artifacts/synthetic/without_time \
  --num-records 20 \
  --lang en \
  --disable-generators day_time
```

Template keys can also be controlled independently of generator families. This
is useful for release profiles that expose only a known subset of the DSL:

```bash
python -m synthetic_query_generation from-plans \
  --plans-dir results/UrbanTrip_deepseek_en_oracletranslation \
  --output-dir artifacts/synthetic/subset \
  --num-records 100 \
  --only-constraint-keys trip_days,people_number,total_budget,attraction_time_window \
  --exclude-plan-prefixes synthetic
```

`--exclude-plan-prefixes` prevents generated plans from being recursively used
as new seeds.

Use priority keys when a batch must contain a minimum number of constraints
from a chosen subset while still mixing in every other enabled family:

```bash
python -m synthetic_query_generation from-plans \
  --plans-dir results/UrbanTrip_deepseek_en_oracletranslation \
  --output-dir artifacts/synthetic/mixed \
  --num-records 100 \
  --priority-constraint-keys total_attraction_count,daily_budget,cross_category_order \
  --min-priority-constraints 2
```

## Constraint Families

The current sampler can generate:

- basic trip constraints: days, traveler count, ticket count
- exact attraction, restaurant, and hotel names
- attraction, restaurant, and hotel feature/type sets
- room count and room type constraints
- in-city transportation mode constraints
- exact per-mode journey counts, walking-distance limits, and in-city travel-time limits
- taxi car-count constraints
- intercity transportation mode constraints
- outbound and return intercity departure-time bounds
- day-specific POI constraints
- total/day-specific attraction counts and required meal types by day
- distinct-hotel counts and minimum free-attraction counts
- time-window constraints
- attraction duration, same-day attraction pairs, and cross-category ordering
- tight budget constraints for total, food, hotel, attraction, and in-city transport costs
- day-specific activity and transportation budgets
- OR requirements composed from two already valid atomic constraints

The default profile favors constraints that are often harder for UrbanTrip:
exact names, time windows, ordering, tight budgets, day-specific requirements,
and combined type sets.

## Adding Or Modifying Constraints

Add or edit natural-language template metadata in `templates.py`. Add executable
sampling logic in `constraints.py` as an independent generator function:

```python
from synthetic_query_generation.constraints import DEFAULT_REGISTRY
from synthetic_query_generation.models import ConstraintCandidate


@DEFAULT_REGISTRY.register("my_constraint_family")
def make_my_constraints(context):
    plan = context.plan
    rng = context.rng
    return [
        ConstraintCandidate(
            key="my_constraint_key",
            code="result=True",
            nl={
                "en": "My English requirement.",
                "zh": "我的中文要求。",
            },
            category="custom",
            tags={"my_tag"},
            hardness=3,
            metadata={"source": "example"},
        )
    ]
```

Each candidate is validated against the seed plan before it can be sampled, and
the final selected constraint set is validated again before writing a record.
This keeps new templates isolated: a bad family will be rejected through the
existing validation path instead of silently corrupting generated data.

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
  --input-dir artifacts/synthetic/generated/data \
  --output-dir artifacts/synthetic/polish_prompts \
  --mode prompts
```

Copy records without polishing:

```bash
python synthetic_query_generation/polish_queries_stub.py \
  --input-dir artifacts/synthetic/generated/data \
  --output-dir artifacts/synthetic/unpolished_copy \
  --mode copy
```

Any future LLM polishing implementation should use `hard_logic_nl` as a
constraint checklist and must not add, remove, weaken, or strengthen
requirements.

## Audit And Release Export

Generated records can be independently rechecked against the copied seed plans:

```bash
python -m synthetic_query_generation.audit \
  --dataset-dir artifacts/synthetic/generated \
  --expected-records 100 \
  --profile full \
  --lang en
```

The audit verifies record structure, unique signatures, canonical concept
labels, natural-language ordering, DSL execution, seed-plan grounding, and all
commonsense checks. It also verifies configured priority-key minimums and
reports old/new constraint coverage. It writes `audit/audit_report.json` and
`audit/constraint_dsl_catalog.md`.

Use `--profile legacy-full` to audit the original 39-key full profile and
`--profile familiar` for the already released 29-key familiar profile.

After an audit passes, export query-only JSON files with the same seven fields
as the phase-one public data:

```bash
python -m synthetic_query_generation.export_release \
  --dataset-dir artifacts/synthetic/generated \
  --output-dir artifacts/synthetic/generated/release \
  --expected-records 100
```

Seed plans, generator metadata, and source-plan paths remain outside the release
folder.

For the complete post-competition Phase 2 Hugging Face release, use the stricter
JSONL exporter:

```bash
PYTHONPATH=. python scripts/export_phase2_hf.py \
  --dataset-dir artifacts/phase2_complete \
  --output-jsonl artifacts/phase2_hf/phase2.jsonl \
  --report artifacts/phase2_hf/phase2_audit_report.json \
  --expected-records 2000 \
  --records-per-shard 1000
```

This export makes inclusive OR, monetary units, transport scope, primary-mode
journey counts, and full-activity time windows explicit. It also removes an OR
only when one of its exact atomic branches is independently required by the
same query. That identity-preserving cleanup does not change the query's
feasible plan set. Future sampling prevents those OR/atomic combinations at
selection time.
