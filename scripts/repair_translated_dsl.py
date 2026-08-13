#!/usr/bin/env python3
"""Repair syntax-invalid translated DSL from the canonical Chinese source."""

import argparse
import ast
import json
from pathlib import Path

from build_translation_assets import build_dictionary, translate_dsl_code


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def invalid_logic_indexes(logic_items):
    invalid = []
    for index, logic in enumerate(logic_items):
        try:
            ast.parse(logic, mode="exec")
        except (SyntaxError, TypeError):
            invalid.append(index)
    return invalid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=PROJECT_ROOT / "TPC_IJCAI_2026_phase1",
    )
    parser.add_argument("--target-dir", action="append", type=Path, required=True)
    parser.add_argument(
        "--report",
        type=Path,
        default=(
            PROJECT_ROOT
            / "translation_artifacts_phase1"
            / "dsl_syntax_repair_report.json"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dictionary = build_dictionary()
    report = {
        "source_dir": str(args.source_dir.resolve()),
        "dry_run": args.dry_run,
        "targets": [],
    }
    for target_dir in args.target_dir:
        target_report = {
            "directory": str(target_dir.resolve()),
            "modified_count": 0,
            "modified_uids": [],
            "records": [],
        }
        for target_path in sorted(target_dir.glob("*.json")):
            target = read_json(target_path)
            invalid_before = invalid_logic_indexes(target.get("hard_logic_py", []))
            if not invalid_before:
                continue
            uid = target.get("uid")
            source_path = args.source_dir / f"{uid}.json"
            source = read_json(source_path)
            repaired_logic = []
            unresolved = []
            for index, source_logic in enumerate(source.get("hard_logic_py", [])):
                translated, _, missing = translate_dsl_code(
                    source_logic,
                    dictionary.term_map,
                )
                repaired_logic.append(translated)
                if missing:
                    unresolved.append({"index": index, "literals": missing})
            invalid_after = invalid_logic_indexes(repaired_logic)
            if unresolved or invalid_after:
                raise RuntimeError(
                    f"Unable to repair {uid}: unresolved={unresolved}, "
                    f"invalid_after={invalid_after}"
                )
            target["hard_logic_py"] = repaired_logic
            if not args.dry_run:
                write_json(target_path, target)
            target_report["modified_count"] += 1
            target_report["modified_uids"].append(uid)
            target_report["records"].append(
                {
                    "uid": uid,
                    "invalid_indexes_before": invalid_before,
                    "constraint_count": len(repaired_logic),
                }
            )
        report["targets"].append(target_report)

    report["modified_file_count"] = sum(
        target["modified_count"] for target in report["targets"]
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
