#!/usr/bin/env python3
"""Build and audit a public JSONL release from the complete Phase 2 dataset."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from synthetic_query_generation.release_wording import (
    INCLUSIVE_OR_PREFIX,
    clarify_constraint_text,
)
from synthetic_query_generation.utils import trip_intro


PUBLIC_FIELDS = (
    "uid",
    "tag",
    "start_city",
    "target_city",
    "days",
    "people_number",
    "hard_logic_py",
    "hard_logic_nl",
    "nature_language",
    "constraint_keys",
    "official_phase2_evaluation",
)
ACTIVITY_TYPES = {
    "accommodation",
    "airplane",
    "attraction",
    "breakfast",
    "dinner",
    "empty",
    "lunch",
    "metro",
    "taxi",
    "train",
    "walk",
}
TIME_RE = re.compile(r"\b(\d{2}):(\d{2})\b")
MONETARY_BUDGET_KEYS = {
    "total_budget",
    "restaurant_budget",
    "accommodation_budget",
    "attraction_budget",
    "innercity_budget",
    "daily_budget",
}


def read_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def read_uids(path):
    if not path:
        return []
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def source_paths(dataset_dir):
    dataset_dir = Path(dataset_dir)
    data_dir = dataset_dir / "data" if (dataset_dir / "data").is_dir() else dataset_dir
    uid_path = dataset_dir / "uids.txt"
    if uid_path.is_file():
        return [data_dir / "{}.json".format(uid) for uid in read_uids(uid_path)]
    return sorted(data_dir.glob("*.json"))


def string_literals(code):
    tree = ast.parse(code)
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def validate_literal_alignment(uid, index, code, text, errors):
    for literal in string_literals(code):
        if literal in ACTIVITY_TYPES or re.fullmatch(r"\d{2}:\d{2}", literal):
            continue
        if literal not in text:
            errors.append(
                "{} constraint {} omits DSL literal {!r} from its text".format(
                    uid, index, literal
                )
            )


def clarify_record(record, official_uids):
    profile = record.get("generation_profile", {})
    keys = profile.get("constraint_keys", [])
    metadata = profile.get("constraint_metadata", [])
    codes = record.get("hard_logic_py", [])
    texts = record.get("hard_logic_nl", [])
    if not (len(keys) == len(metadata) == len(codes) == len(texts)):
        raise ValueError("{} has inconsistent constraint arrays".format(record.get("uid")))

    atomic_codes = {
        code for key, code in zip(keys, codes) if key != "either_requirement"
    }
    kept = []
    removed_redundant_or = []
    for index, (key, code, text, item_metadata) in enumerate(
        zip(keys, codes, texts, metadata), 1
    ):
        if key == "either_requirement" and any(
            atomic_code in code for atomic_code in atomic_codes
        ):
            removed_redundant_or.append(index)
            continue
        kept.append((key, code, text, item_metadata))

    keys = [item[0] for item in kept]
    codes = [item[1] for item in kept]
    clarified = [
        clarify_constraint_text(key, text, item_metadata)
        for key, _code, text, item_metadata in kept
    ]
    intro = trip_intro(
        "en",
        people=record["people_number"],
        start_city=record["start_city"],
        target_city=record["target_city"],
        days=record["days"],
    )
    nature_language = "\n".join(
        [intro, "Requirements:"]
        + ["{}. {}".format(index, text) for index, text in enumerate(clarified, 1)]
    )
    row = {
        "uid": record["uid"],
        "tag": record["tag"],
        "start_city": record["start_city"],
        "target_city": record["target_city"],
        "days": record["days"],
        "people_number": record["people_number"],
        "hard_logic_py": codes,
        "hard_logic_nl": clarified,
        "nature_language": nature_language,
        "constraint_keys": keys,
        "official_phase2_evaluation": record["uid"] in official_uids,
    }
    wording_changes = Counter(
        key
        for key, _code, original, item_metadata in kept
        if clarify_constraint_text(key, original, item_metadata) != original
    )
    return row, {
        "removed_redundant_or_indices": removed_redundant_or,
        "wording_changes": dict(wording_changes),
    }


def audit_rows(rows, expected_records, expected_official):
    errors = []
    warnings = []
    uid_counts = Counter(row["uid"] for row in rows)
    nl_counts = Counter(row["nature_language"] for row in rows)
    key_counts = Counter()
    overlapping_entities = defaultdict(list)

    if len(rows) != expected_records:
        errors.append("Expected {} records, found {}".format(expected_records, len(rows)))
    duplicate_uids = sorted(uid for uid, count in uid_counts.items() if count > 1)
    if duplicate_uids:
        errors.append("Duplicate UIDs: {}".format(duplicate_uids[:20]))
    duplicate_queries = sum(count > 1 for count in nl_counts.values())
    if duplicate_queries:
        errors.append("{} natural-language queries are duplicated".format(duplicate_queries))
    official_count = sum(row["official_phase2_evaluation"] for row in rows)
    if expected_official is not None and official_count != expected_official:
        errors.append(
            "Expected {} official evaluation records, found {}".format(
                expected_official, official_count
            )
        )

    entity_keys = {
        "attraction_on_day": "attraction",
        "attraction_time_window": "attraction",
        "attraction_exact_time": "attraction",
        "restaurant_on_day": "restaurant",
        "restaurant_time_window": "restaurant",
        "restaurant_exact_time": "restaurant",
        "accommodation_on_day": "accommodation",
        "accommodation_time_window": "accommodation",
        "accommodation_exact_time": "accommodation",
    }
    for row in rows:
        uid = row["uid"]
        keys = row["constraint_keys"]
        codes = row["hard_logic_py"]
        texts = row["hard_logic_nl"]
        if not (len(keys) == len(codes) == len(texts)):
            errors.append("{} has inconsistent public constraint arrays".format(uid))
            continue
        expected_nl = "\n".join(
            [
                trip_intro(
                    "en",
                    people=row["people_number"],
                    start_city=row["start_city"],
                    target_city=row["target_city"],
                    days=row["days"],
                ),
                "Requirements:",
            ]
            + ["{}. {}".format(index, text) for index, text in enumerate(texts, 1)]
        )
        if row["nature_language"] != expected_nl:
            errors.append("{} has a truncated or misordered nature_language field".format(uid))
        if any(not value for value in (uid, row["start_city"], row["target_city"], row["nature_language"])):
            errors.append("{} contains an empty required field".format(uid))

        direct_entities = defaultdict(int)
        atomic_codes = {
            code for key, code in zip(keys, codes) if key != "either_requirement"
        }
        for index, (key, code, text) in enumerate(zip(keys, codes, texts), 1):
            key_counts[key] += 1
            try:
                validate_literal_alignment(uid, index, code, text, errors)
            except SyntaxError as exc:
                errors.append("{} constraint {} has invalid DSL: {}".format(uid, index, exc))
            for hour, minute in TIME_RE.findall(text):
                if int(hour) > 24 or int(minute) > 59 or (hour == "24" and minute != "00"):
                    errors.append(
                        "{} constraint {} has invalid time {}:{}".format(
                            uid, index, hour, minute
                        )
                    )
            if key == "either_requirement" and not text.startswith(INCLUSIVE_OR_PREFIX):
                errors.append("{} has an ambiguous OR requirement".format(uid))
            if key == "either_requirement" and any(
                atomic_code in code for atomic_code in atomic_codes
            ):
                errors.append(
                    "{} constraint {} repeats an independently required OR branch".format(
                        uid, index
                    )
                )
            if key in MONETARY_BUDGET_KEYS and not text.endswith(" CNY."):
                errors.append("{} constraint {} omits the CNY budget unit".format(uid, index))
            if key in {
                "inner_transport_modes_subset",
                "innercity_budget",
                "forbidden_inner_transport_modes",
            } and "destination city" in text:
                errors.append("{} constraint {} incorrectly narrows transport scope".format(uid, index))
            if key.endswith("_time_window") and "entire" not in text:
                errors.append("{} constraint {} has an ambiguous time window".format(uid, index))

            kind = entity_keys.get(key)
            if kind:
                literals = [
                    literal
                    for literal in string_literals(code)
                    if literal not in ACTIVITY_TYPES and not TIME_RE.fullmatch(literal)
                ]
                if literals:
                    direct_entities[(kind, literals[0])] += 1
        for entity, count in direct_entities.items():
            if count > 1:
                overlapping_entities[uid].append(
                    {"entity_type": entity[0], "name": entity[1], "constraint_count": count}
                )

    if overlapping_entities:
        warnings.append(
            "{} records contain compatible but overlapping direct constraints on the same entity".format(
                len(overlapping_entities)
            )
        )
    return {
        "status": "passed" if not errors else "failed",
        "records_checked": len(rows),
        "official_phase2_evaluation_records": official_count,
        "unique_uids": len(uid_counts),
        "unique_natural_language_queries": len(nl_counts),
        "constraint_key_count": len(key_counts),
        "constraint_key_counts": dict(sorted(key_counts.items())),
        "overlapping_direct_entity_constraint_records": len(overlapping_entities),
        "overlapping_direct_entity_constraint_examples": dict(
            list(sorted(overlapping_entities.items()))[:20]
        ),
        "errors": errors,
        "warnings": warnings,
    }


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_rows(rows, output_path, records_per_shard=0):
    output_path = Path(output_path)
    encoded_rows = [
        (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        for row in rows
    ]
    combined_digest = hashlib.sha256()
    for encoded in encoded_rows:
        combined_digest.update(encoded)

    if not records_per_shard:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as handle:
            handle.writelines(encoded_rows)
        return [output_path], combined_digest.hexdigest()

    shard_dir = output_path.parent / output_path.stem
    shard_dir.mkdir(parents=True, exist_ok=True)
    shard_count = (len(encoded_rows) + records_per_shard - 1) // records_per_shard
    expected_paths = [
        shard_dir / "part-{:05d}.jsonl".format(index)
        for index in range(shard_count)
    ]
    unexpected = sorted(set(shard_dir.glob("*.jsonl")) - set(expected_paths))
    if unexpected:
        raise ValueError(
            "Shard directory contains stale JSONL files: {}".format(unexpected)
        )
    for index, path in enumerate(expected_paths):
        start = index * records_per_shard
        end = start + records_per_shard
        with path.open("wb") as handle:
            handle.writelines(encoded_rows[start:end])
    return expected_paths, combined_digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expected-records", type=int, default=2000)
    parser.add_argument("--official-eval-uids")
    parser.add_argument("--expected-official", type=int)
    parser.add_argument("--source-audit-report")
    parser.add_argument(
        "--records-per-shard",
        type=int,
        default=0,
        help="Write part files under <output-jsonl stem>/ instead of one JSONL file.",
    )
    args = parser.parse_args(argv)

    paths = source_paths(args.dataset_dir)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise SystemExit("Missing source records: {}".format(missing[:20]))
    official_uids = set(read_uids(args.official_eval_uids))
    rows = []
    cleanup_by_uid = {}
    wording_changes = Counter()
    for path in paths:
        row, cleanup = clarify_record(read_json(path), official_uids)
        rows.append(row)
        wording_changes.update(cleanup["wording_changes"])
        if cleanup["removed_redundant_or_indices"]:
            cleanup_by_uid[row["uid"]] = cleanup["removed_redundant_or_indices"]
    report = audit_rows(rows, args.expected_records, args.expected_official)
    report.update(
        {
            "wording_clarification_counts": dict(sorted(wording_changes.items())),
            "wording_clarifications_total": sum(wording_changes.values()),
            "redundant_or_constraints_removed": sum(
                len(indices) for indices in cleanup_by_uid.values()
            ),
            "records_with_redundant_or_removed": len(cleanup_by_uid),
            "redundant_or_original_indices_by_uid": cleanup_by_uid,
            "combined_query_feasible_set_changed": False,
            "source_dataset": Path(args.dataset_dir).name,
        }
    )
    if args.source_audit_report:
        source_audit = read_json(args.source_audit_report)
        source_audit_summary = {
            key: source_audit.get(key)
            for key in (
                "status",
                "records_checked",
                "unique_signatures",
                "unique_source_plans",
                "expected_constraint_key_count",
                "covered_constraint_key_count",
                "errors",
                "warnings",
            )
        }
        report["source_seed_plan_audit"] = source_audit_summary
        if (
            source_audit_summary["status"] != "passed"
            or source_audit_summary["records_checked"] != args.expected_records
            or source_audit_summary["errors"]
        ):
            report["errors"].append("The source seed-plan audit did not pass")
            report["status"] = "failed"
    if report["status"] != "passed":
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        raise SystemExit("Phase 2 release audit failed; see {}".format(args.report))

    output_path = Path(args.output_jsonl)
    output_paths, combined_sha256 = write_rows(
        rows, output_path, args.records_per_shard
    )
    report.update(
        {
            "output_files": [
                str(path.relative_to(output_path.parent)) for path in output_paths
            ],
            "output_file_sha256": {
                str(path.relative_to(output_path.parent)): sha256(path)
                for path in output_paths
            },
            "combined_jsonl_sha256": combined_sha256,
            "public_fields": list(PUBLIC_FIELDS),
            "seed_plans_included": False,
            "generation_paths_included": False,
        }
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Wrote {} audited records to {} file(s) under {}".format(
            len(rows), len(output_paths), output_path.parent
        )
    )
    print("Audit report: {}".format(report_path))


if __name__ == "__main__":
    main()
