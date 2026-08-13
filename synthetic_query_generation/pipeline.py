"""Public generation pipeline APIs."""

import json
import random
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from chinatravel.environment.language import CITY_NAMES, normalize_lang

from synthetic_query_generation.constraints import (
    DEFAULT_REGISTRY,
    candidate_constraints,
    choose_constraints,
    make_basic_constraints,
    make_or_constraints,
)
from synthetic_query_generation.models import (
    FromPlansConfig,
    RecordGenerationOptions,
    SeedQueryConfig,
)
from synthetic_query_generation.templates import TEMPLATE_CATALOG
from synthetic_query_generation.utils import (
    build_nature_language,
    infer_record_lang,
    plural_en,
    read_json,
    trip_intro,
    write_json,
    write_text,
)
from synthetic_query_generation.validation import (
    seed_plan_commonsense_errors,
    set_hard_lang,
    validate_constraints,
)


def generate_record_from_plan(
    plan_path,
    plan,
    options: RecordGenerationOptions,
    rng,
    ordinal,
    registry=DEFAULT_REGISTRY,
):
    lang = infer_record_lang(plan, options.lang)
    set_hard_lang(lang)
    source_uid = Path(plan_path).stem

    def key_enabled(key):
        if generation_options.enabled_constraint_keys is not None:
            if key not in generation_options.enabled_constraint_keys:
                return False
        return key not in generation_options.disabled_constraint_keys

    generation_options = options.constraint_generation
    selection_options = options.constraint_selection
    base_constraints = make_basic_constraints(plan, lang) if options.include_basic_constraints else []
    base_constraints = [
        constraint for constraint in base_constraints if key_enabled(constraint.key)
    ]
    candidates = candidate_constraints(
        plan,
        lang,
        rng,
        options=generation_options,
        registry=registry,
    )
    candidates = [
        constraint for constraint in candidates if key_enabled(constraint.key)
    ]

    valid_candidates = []
    rejected = []
    for candidate in candidates:
        ok, results = validate_constraints(plan, [candidate.code], lang)
        if ok:
            valid_candidates.append(candidate)
        else:
            rejected.append({"key": candidate.key, "results": results, "code": candidate.code})

    if generation_options.include_or_constraints and key_enabled("either_requirement"):
        for candidate in make_or_constraints(
            valid_candidates,
            rng,
            generation_options.max_or_candidates_per_plan,
        ):
            ok, results = validate_constraints(plan, [candidate.code], lang)
            if ok:
                valid_candidates.append(candidate)
            else:
                rejected.append({"key": candidate.key, "results": results, "code": candidate.code})

    sampled_count = rng.randint(
        selection_options.min_constraints,
        selection_options.max_constraints,
    )
    sampled = choose_constraints(
        valid_candidates,
        rng,
        sampled_count,
        selection_options.min_tricky_constraints,
        selection_options.min_logic_constraints,
        priority_keys=selection_options.priority_constraint_keys,
        min_priority=selection_options.min_priority_constraints,
    )
    sampled_priority_count = sum(
        constraint.key in selection_options.priority_constraint_keys
        for constraint in sampled
    )
    if sampled_priority_count < selection_options.min_priority_constraints:
        return None, {
            "source_uid": source_uid,
            "reason": "not_enough_priority_constraints",
            "required": selection_options.min_priority_constraints,
            "selected": sampled_priority_count,
            "available_keys": sorted(
                {
                    constraint.key
                    for constraint in valid_candidates
                    if constraint.key in selection_options.priority_constraint_keys
                }
            ),
        }
    selected = base_constraints + sampled
    if len(sampled) < selection_options.min_constraints:
        return None, {
            "source_uid": source_uid,
            "reason": "not_enough_valid_candidates",
            "valid_candidates": len(valid_candidates),
            "rejected_candidates": rejected,
        }

    all_ok, all_results = validate_constraints(plan, [c.code for c in selected], lang)
    if not all_ok:
        return None, {
            "source_uid": source_uid,
            "reason": "selected_constraints_failed_validation",
            "results": all_results,
            "constraints": [c.key for c in selected],
        }

    uid = f"{options.uid_prefix}_{source_uid}_{ordinal:05d}"
    record = {
        "uid": uid,
        "tag": options.tag,
        "start_city": plan["start_city"],
        "target_city": plan["target_city"],
        "days": len(plan.get("itinerary", [])),
        "people_number": int(plan["people_number"]),
        "hard_logic_py": [constraint.code for constraint in selected],
        "hard_logic_nl": [constraint.text(lang) for constraint in selected],
        "nature_language": "",
        "source_plan_uid": source_uid,
        "seed_plan_path": str(Path(plan_path)),
        "generation_profile": {
            "lang": lang,
            "sampled_constraints": len(sampled),
            "valid_candidate_constraints": len(valid_candidates),
            "rejected_candidate_constraints": len(rejected),
            "constraint_keys": [constraint.key for constraint in selected],
            "constraint_categories": [constraint.category for constraint in selected],
            "constraint_tags": [sorted(constraint.tags) for constraint in selected],
            "constraint_metadata": [constraint.metadata for constraint in selected],
            "logic_constraint_count": sum(
                1 for constraint in sampled if constraint.tags & {"not_constraint", "or_group"}
            ),
            "priority_constraint_count": sampled_priority_count,
            "or_constraint_count": sum(1 for constraint in sampled if "or_group" in constraint.tags),
            "not_constraint_count": sum(1 for constraint in sampled if "not_constraint" in constraint.tags),
        },
    }
    record["nature_language"] = build_nature_language(record, selected, lang)
    return record, None


def load_seed_plans(config: FromPlansConfig, rng):
    plans = []
    for path in sorted(config.plans_dir.glob(config.plan_glob)):
        if config.excluded_plan_prefixes and path.stem.startswith(
            config.excluded_plan_prefixes
        ):
            continue
        try:
            plan = read_json(path)
        except json.JSONDecodeError:
            continue
        if isinstance(plan, dict) and plan.get("itinerary") and plan.get("start_city") and plan.get("target_city"):
            plans.append((path, plan))
    if config.shuffle:
        rng.shuffle(plans)
    if config.max_seed_plans:
        plans = plans[: config.max_seed_plans]
    return plans


def generate_from_plans(config: FromPlansConfig, registry=DEFAULT_REGISTRY):
    rng = random.Random(config.seed)
    plans = load_seed_plans(config, rng)
    output_dir = config.output_dir
    data_dir = output_dir if config.flat_output else output_dir / "data"
    seed_plan_dir = output_dir / "seed_plans"
    generated = []
    skipped = []
    seen_signatures = set()
    ordinal = 0
    record_options = config.record_options()
    progress = (
        tqdm(
            total=config.num_records,
            desc="Generating queries",
            unit="record",
            mininterval=2.0,
        )
        if tqdm is not None
        else None
    )

    for path, plan in plans:
        if config.validate_seed_commonsense:
            lang = infer_record_lang(plan, config.lang)
            seed_errors = seed_plan_commonsense_errors(plan, lang)
            if seed_errors:
                skipped.append(
                    {
                        "source_uid": Path(path).stem,
                        "reason": "seed_plan_commonsense_failed",
                        "errors": seed_errors,
                    }
                )
                continue
        for _ in range(config.variants_per_plan):
            ordinal += 1
            record, error = generate_record_from_plan(
                path,
                plan,
                record_options,
                rng,
                ordinal,
                registry=registry,
            )
            if error:
                skipped.append(error)
                continue
            signature = (
                record["start_city"],
                record["target_city"],
                record["days"],
                record["people_number"],
                tuple(record["hard_logic_py"]),
            )
            if signature in seen_signatures:
                skipped.append(
                    {
                        "source_uid": record["source_plan_uid"],
                        "reason": "duplicate_signature",
                    }
                )
                continue
            seen_signatures.add(signature)
            write_json(data_dir / f"{record['uid']}.json", record)
            if config.copy_seed_plans:
                write_json(seed_plan_dir / f"{record['uid']}.json", plan)
            generated.append(record)
            if progress is not None:
                progress.update(1)
            if len(generated) >= config.num_records:
                break
        if len(generated) >= config.num_records:
            break

    if progress is not None:
        progress.close()

    template_inventory = {}
    for record in generated:
        for key, nl in zip(
            record["generation_profile"]["constraint_keys"],
            record["hard_logic_nl"],
        ):
            template_inventory.setdefault(key, set()).add(nl)

    manifest = {
        "num_records_requested": config.num_records,
        "num_records_generated": len(generated),
        "num_seed_plans_loaded": len(plans),
        "num_seed_plans_skipped": len(skipped),
        "lang": config.lang,
        "seed": config.seed,
        "plans_dir": str(config.plans_dir),
        "data_dir": str(data_dir.resolve()),
        "copy_seed_plans": config.copy_seed_plans,
        "variants_per_plan": config.variants_per_plan,
        "unique_signatures": len(seen_signatures),
        "sampling_config": {
            "min_constraints": config.min_constraints,
            "max_constraints": config.max_constraints,
            "min_tricky_constraints": config.min_tricky_constraints,
            "min_logic_constraints": config.min_logic_constraints,
            "priority_constraint_keys": sorted(config.priority_constraint_keys),
            "min_priority_constraints": config.min_priority_constraints,
            "budget_margin": config.budget_margin,
            "include_basic_constraints": config.include_basic_constraints,
            "include_negative_constraints": config.include_negative_constraints,
            "include_or_constraints": config.include_or_constraints,
            "max_or_candidates_per_plan": config.max_or_candidates_per_plan,
            "only_generators": sorted(config.only_generators) if config.only_generators else None,
            "disabled_generators": sorted(config.disabled_generators),
            "only_constraint_keys": sorted(config.only_constraint_keys) if config.only_constraint_keys else None,
            "disabled_constraint_keys": sorted(config.disabled_constraint_keys),
            "excluded_plan_prefixes": list(config.excluded_plan_prefixes),
        },
        "constraint_generator_registry": registry.names(),
        "skipped": skipped[: config.max_manifest_errors],
        "constraint_template_catalog": TEMPLATE_CATALOG,
        "constraint_template_examples": {
            key: sorted(values)[:5] for key, values in sorted(template_inventory.items())
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    if config.split_file:
        write_text(config.split_file, "\n".join(record["uid"] for record in generated) + "\n")
    return manifest


def generate_seed_queries(config: SeedQueryConfig):
    rng = random.Random(config.seed)
    lang = normalize_lang(config.lang)
    cities = list(CITY_NAMES[lang])
    records = []
    for idx in range(1, config.num_records + 1):
        start_city, target_city = rng.sample(cities, 2)
        days = rng.randint(config.min_days, config.max_days)
        people = rng.randint(config.min_people, config.max_people)
        uid = f"{config.uid_prefix}_{idx:05d}"
        record = {
            "uid": uid,
            "tag": config.tag,
            "start_city": start_city,
            "target_city": target_city,
            "days": days,
            "people_number": people,
            "hard_logic_py": [
                f"result=(day_count(plan)=={days})",
                f"result=(people_count(plan)=={people})",
            ],
            "hard_logic_nl": [
                f"The trip must last {plural_en(days, 'day')}." if lang == "en" else f"行程必须为{days}天。",
                f"The plan must be for {plural_en(people, 'traveler')}." if lang == "en" else f"行程人数必须为{people}人。",
            ],
            "nature_language": trip_intro(
                lang,
                people=people,
                start_city=start_city,
                target_city=target_city,
                days=days,
            ),
        }
        write_json(config.output_dir / f"{uid}.json", record)
        records.append(record)
    manifest = {
        "mode": "seed_queries",
        "num_records_generated": len(records),
        "lang": lang,
        "seed": config.seed,
    }
    write_json(config.output_dir / "manifest.json", manifest)
    return manifest
