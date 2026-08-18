"""Audit generated query records against their copied seed plans."""

import argparse
import ast
import json
import statistics
from collections import Counter
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from chinatravel.environment.concept_labels import (
    LEGACY_ENGLISH_CONCEPT_LITERAL_ALIASES,
)
from chinatravel.environment.tools.accommodations.apis import Accommodations
from chinatravel.environment.tools.attractions.apis import Attractions
from chinatravel.environment.tools.restaurants.apis import Restaurants

from synthetic_query_generation.catalog import (
    CONSTRAINT_GENERATORS,
    CONSTRAINT_SEMANTICS_ZH,
    FAMILIAR_CONSTRAINT_KEYS,
    FULL_CONSTRAINT_KEYS,
    LEGACY_FULL_CONSTRAINT_KEYS,
    NEW_CONSTRAINT_KEYS,
    validate_catalog,
)
from synthetic_query_generation.templates import TEMPLATE_CATALOG
from synthetic_query_generation.utils import read_json, write_json, write_text
from synthetic_query_generation.validation import (
    seed_plan_commonsense_errors,
    validate_constraints,
)


def _string_literals(code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _sandbox_alias_errors():
    checks = [
        ("attraction", Attractions(lang="en"), "type"),
        ("restaurant", Restaurants(lang="en"), "cuisine"),
        ("accommodation", Accommodations(lang="en"), "featurehoteltype"),
    ]
    errors = []
    inventory = {}
    for kind, tool, field in checks:
        values = set()
        for frame in tool.data.values():
            values.update(frame[field].dropna().astype(str))
        aliases = set(LEGACY_ENGLISH_CONCEPT_LITERAL_ALIASES) & values
        if aliases:
            errors.append(
                "Sandbox {} field still exposes aliases: {}".format(
                    kind, sorted(aliases)
                )
            )
        inventory[kind] = sorted(values)
    return errors, inventory


def _expected_keys(profile):
    if profile == "full":
        return set(FULL_CONSTRAINT_KEYS)
    if profile == "legacy-full":
        return set(LEGACY_FULL_CONSTRAINT_KEYS)
    if profile == "familiar":
        return set(FAMILIAR_CONSTRAINT_KEYS)
    raise ValueError("Unknown audit profile: {}".format(profile))


def _record_paths(dataset_dir):
    data_dir = dataset_dir / "data"
    if not data_dir.is_dir():
        data_dir = dataset_dir
    return data_dir, sorted(
        path for path in data_dir.glob("*.json") if path.name != "manifest.json"
    )


def _structural_dsl_errors(key, code):
    errors = []
    if "len(" in code:
        errors.append(
            "uses len(), which is unavailable in the legacy online evaluator"
        )
    if key.endswith("_time_window") or key.endswith("_exact_time"):
        if "activity_type(activity)" not in code:
            errors.append("time constraint does not restrict the activity type")
    if key == "attraction_order" and code.count("activity_type(activity)") < 2:
        errors.append("ordering constraint does not ground both operands as attractions")
    if key in {"forbidden_depart_transport", "forbidden_return_transport"}:
        if "intercity_activities" not in code:
            errors.append("directional transport constraint does not locate intercity activities")
        if "allactivities(plan)[0]" in code or "allactivities(plan)[-1]" in code:
            errors.append("directional transport constraint uses a raw activity position")
    if key in {"outbound_departure_deadline", "return_departure_earliest"}:
        if "activity_type(activity) in ['train', 'airplane']" not in code:
            errors.append("directional time constraint is not grounded as intercity transport")
    if key == "walking_distance_budget":
        if "innercity_transport_distance(activity_transports(activity), 'walk')" not in code:
            errors.append("walking-distance constraint does not select walking legs")
    if key == "cross_category_order" and code.count("activity_type(activity)") < 2:
        errors.append("cross-category ordering does not type both operands")
    return errors


def audit_dataset(dataset_dir, expected_records, profile, lang="en"):
    validate_catalog(TEMPLATE_CATALOG)
    dataset_dir = Path(dataset_dir)
    data_dir, paths = _record_paths(dataset_dir)
    seed_dir = dataset_dir / "seed_plans"
    expected_keys = _expected_keys(profile)
    errors = []
    warnings = []
    key_counts = Counter()
    category_counts = Counter()
    tag_counts = Counter()
    examples = {}
    signatures = {}
    constraints_per_record = []
    new_constraints_per_record = []
    priority_constraints_per_record = []
    source_plan_counts = Counter()
    commonsense_cache = {}
    manifest_path = dataset_dir / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    sampling_config = manifest.get("sampling_config", {})
    priority_keys = set(sampling_config.get("priority_constraint_keys", []))
    minimum_priority = int(sampling_config.get("min_priority_constraints", 0) or 0)

    if len(paths) != expected_records:
        errors.append(
            "Expected {} records, found {} in {}".format(
                expected_records, len(paths), data_dir
            )
        )

    iterator = (
        tqdm(paths, desc="Auditing queries", unit="record", mininterval=2.0)
        if tqdm is not None
        else paths
    )
    for path in iterator:
        try:
            record = read_json(path)
        except Exception as exc:
            errors.append("{}: invalid JSON: {}".format(path.name, exc))
            continue

        uid = record.get("uid")
        if uid != path.stem:
            errors.append("{}: UID does not match filename".format(path.name))
        source_uid = record.get("source_plan_uid")
        source_plan_counts[source_uid] += 1

        codes = record.get("hard_logic_py")
        texts = record.get("hard_logic_nl")
        profile_data = record.get("generation_profile", {})
        keys = profile_data.get("constraint_keys")
        categories = profile_data.get("constraint_categories", [])
        tags = profile_data.get("constraint_tags", [])
        if not isinstance(codes, list) or not isinstance(texts, list) or not isinstance(keys, list):
            errors.append("{}: hard logic fields or constraint_keys are not lists".format(uid))
            continue
        if not (len(codes) == len(texts) == len(keys)):
            errors.append(
                "{}: hard_logic_py, hard_logic_nl, and constraint_keys lengths differ".format(
                    uid
                )
            )
            continue
        if len(categories) != len(keys) or len(tags) != len(keys):
            errors.append("{}: generation profile arrays have inconsistent lengths".format(uid))

        unknown = set(keys) - set(TEMPLATE_CATALOG)
        disallowed = set(keys) - expected_keys
        if unknown:
            errors.append("{}: unknown constraint keys {}".format(uid, sorted(unknown)))
        if disallowed:
            errors.append("{}: keys outside {} profile: {}".format(uid, profile, sorted(disallowed)))

        nature_language = record.get("nature_language", "")
        cursor = 0
        for text in texts:
            next_cursor = nature_language.find(text, cursor)
            if next_cursor < 0:
                errors.append("{}: NL requirement missing or out of order: {}".format(uid, text))
                break
            cursor = next_cursor + len(text)

        for index, (key, code, text) in enumerate(zip(keys, codes, texts)):
            key_counts[key] += 1
            if index < len(categories):
                category_counts[categories[index]] += 1
            if index < len(tags):
                tag_counts.update(tags[index])
            examples.setdefault(key, {"uid": uid, "dsl": code, "nl": text})
            alias_literals = sorted(
                set(_string_literals(code))
                & set(LEGACY_ENGLISH_CONCEPT_LITERAL_ALIASES)
            )
            if alias_literals:
                errors.append(
                    "{}: non-canonical DSL literals for {}: {}".format(
                        uid, key, alias_literals
                    )
                )
            for message in _structural_dsl_errors(key, code):
                errors.append("{}: {}: {}".format(uid, key, message))

        constraints_per_record.append(len(codes))
        new_constraints_per_record.append(
            sum(key in NEW_CONSTRAINT_KEYS for key in keys)
        )
        priority_count = sum(key in priority_keys for key in keys)
        priority_constraints_per_record.append(priority_count)
        recorded_priority_count = profile_data.get("priority_constraint_count")
        if recorded_priority_count is not None and recorded_priority_count != priority_count:
            errors.append(
                "{}: recorded priority count {} differs from computed {}".format(
                    uid, recorded_priority_count, priority_count
                )
            )
        if priority_count < minimum_priority:
            errors.append(
                "{}: only {} priority constraints, expected at least {}".format(
                    uid, priority_count, minimum_priority
                )
            )
        signature = (
            record.get("start_city"),
            record.get("target_city"),
            record.get("days"),
            record.get("people_number"),
            tuple(codes),
        )
        if signature in signatures:
            errors.append(
                "{}: duplicate signature also used by {}".format(
                    uid, signatures[signature]
                )
            )
        else:
            signatures[signature] = uid

        seed_path = seed_dir / "{}.json".format(uid)
        if not seed_path.is_file():
            errors.append("{}: copied seed plan is missing".format(uid))
            continue
        seed_plan = read_json(seed_path)
        ok, results = validate_constraints(seed_plan, codes, lang)
        if not ok:
            failed = [index for index, result in enumerate(results) if not result]
            errors.append("{}: seed plan fails DSL indices {}".format(uid, failed))

        if source_uid not in commonsense_cache:
            commonsense_cache[source_uid] = seed_plan_commonsense_errors(seed_plan, lang)
        if commonsense_cache[source_uid]:
            errors.append(
                "{}: seed plan fails commonsense checks: {}".format(
                    uid, commonsense_cache[source_uid]
                )
            )

    missing_keys = expected_keys - set(key_counts)
    if missing_keys:
        errors.append("Dataset does not cover expected keys: {}".format(sorted(missing_keys)))

    sandbox_errors, sandbox_inventory = _sandbox_alias_errors()
    errors.extend(sandbox_errors)
    if len(source_plan_counts) < max(1, expected_records // 2):
        warnings.append(
            "Only {} unique source plans were used for {} records".format(
                len(source_plan_counts), len(paths)
            )
        )

    report = {
        "status": "passed" if not errors else "failed",
        "profile": profile,
        "dataset_dir": str(dataset_dir.resolve()),
        "expected_records": expected_records,
        "records_checked": len(paths),
        "unique_signatures": len(signatures),
        "unique_source_plans": len(source_plan_counts),
        "expected_constraint_key_count": len(expected_keys),
        "covered_constraint_key_count": len(set(key_counts) & expected_keys),
        "expected_constraint_keys": sorted(expected_keys),
        "withheld_constraint_keys": sorted(FULL_CONSTRAINT_KEYS - expected_keys),
        "constraint_key_counts": dict(sorted(key_counts.items())),
        "constraint_category_counts": dict(sorted(category_counts.items())),
        "constraint_tag_counts": dict(sorted(tag_counts.items())),
        "constraints_per_record": {
            "min": min(constraints_per_record) if constraints_per_record else 0,
            "max": max(constraints_per_record) if constraints_per_record else 0,
            "mean": statistics.mean(constraints_per_record) if constraints_per_record else 0,
            "median": statistics.median(constraints_per_record) if constraints_per_record else 0,
        },
        "new_constraints_per_record": {
            "min": min(new_constraints_per_record) if new_constraints_per_record else 0,
            "max": max(new_constraints_per_record) if new_constraints_per_record else 0,
            "mean": statistics.mean(new_constraints_per_record) if new_constraints_per_record else 0,
            "median": statistics.median(new_constraints_per_record) if new_constraints_per_record else 0,
        },
        "priority_constraints_per_record": {
            "configured_keys": sorted(priority_keys),
            "configured_minimum": minimum_priority,
            "min": min(priority_constraints_per_record) if priority_constraints_per_record else 0,
            "max": max(priority_constraints_per_record) if priority_constraints_per_record else 0,
            "mean": statistics.mean(priority_constraints_per_record) if priority_constraints_per_record else 0,
        },
        "sandbox_canonical_value_counts": {
            kind: len(values) for kind, values in sandbox_inventory.items()
        },
        "errors": errors,
        "warnings": warnings,
    }
    return report, examples


def render_constraint_catalog(profile, report, examples):
    expected_keys = _expected_keys(profile)
    lines = [
        "# Constraint DSL Catalog",
        "",
        "Profile: `{}`. Covered templates: `{}/{}`.".format(
            profile,
            report["covered_constraint_key_count"],
            report["expected_constraint_key_count"],
        ),
        "",
        "Each DSL block below is a concrete example from this generated batch. "
        "The accompanying sentence states the intended evaluator semantics.",
        "",
    ]
    for key in TEMPLATE_CATALOG:
        if key not in expected_keys:
            continue
        metadata = TEMPLATE_CATALOG[key]
        example = examples.get(key)
        lines.extend(
            [
                "## `{}`".format(key),
                "",
                "- Generator: `{}`".format(CONSTRAINT_GENERATORS[key]),
                "- Category: `{}`".format(metadata["category"]),
                "- Semantics: {}".format(CONSTRAINT_SEMANTICS_ZH[key]),
                "- English template: `{}`".format(metadata["en"]),
                "",
            ]
        )
        if example:
            lines.extend(
                [
                    "Example natural language:",
                    "",
                    "> {}".format(example["nl"]),
                    "",
                    "Example DSL:",
                    "",
                    "```python",
                    example["dsl"],
                    "```",
                    "",
                ]
            )
        else:
            lines.extend(["No example was sampled in this batch.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--expected-records", required=True, type=int)
    parser.add_argument(
        "--profile",
        choices=["full", "legacy-full", "familiar"],
        required=True,
    )
    parser.add_argument("--lang", choices=["en", "zh"], default="en")
    args = parser.parse_args(argv)

    dataset_dir = Path(args.dataset_dir)
    report, examples = audit_dataset(
        dataset_dir,
        expected_records=args.expected_records,
        profile=args.profile,
        lang=args.lang,
    )
    audit_dir = dataset_dir / "audit"
    write_json(audit_dir / "audit_report.json", report)
    write_text(
        audit_dir / "constraint_dsl_catalog.md",
        render_constraint_catalog(args.profile, report, examples),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
