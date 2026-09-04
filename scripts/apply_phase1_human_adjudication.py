#!/usr/bin/env python3
"""Build the final Phase 1 English dataset from a human adjudication report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from audit_phase1_translations import audit_record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "TPC_IJCAI_2026_phase1_EN"
DEFAULT_CHINESE_DIR = PROJECT_ROOT / "TPC_IJCAI_2026_phase1"
DEFAULT_UID_FILE = PROJECT_ROOT / "TPC_IJCAI_2026_phase1.txt"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "TPC_IJCAI_2026_phase1_EN_final"
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "translation_artifacts_phase1"
    / "audit"
    / "thinking_reaudit"
    / "human_adjudication"
    / "phase1_human_adjudication.json"
)
DEFAULT_MANIFEST = DEFAULT_REPORT.parent / "final_apply_manifest.json"
CHANGELOG_NAME = "TRANSLATION_CHANGES.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--chinese-dir", type=Path, default=DEFAULT_CHINESE_DIR)
    parser.add_argument("--uid-file", type=Path, default=DEFAULT_UID_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory after all input checks pass.",
    )
    return parser.parse_args()


def read_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file_obj:
        value = json.load(file_obj)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def write_object(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_obj:
        json.dump(value, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def render_change_log(total_records: int, changes: list[dict]) -> str:
    lines = [
        "# Phase 1 English Query Changes",
        "",
        "## Summary",
        "",
        f"- Total JSON records: {total_records}",
        f"- Modified JSON records: {len(changes)}",
        f"- Modified field values: {len(changes)}",
        f"- Unchanged JSON records: {total_records - len(changes)}",
        "- Modified field in every listed record: `nature_language`",
        "- Modified `hard_logic_py` fields: 0",
        "- Modified UID or trip-metadata fields: 0",
        "",
        "The final dataset was rebuilt from `TPC_IJCAI_2026_phase1_EN`.",
        "The earlier broad LLM repair output was not used. Exactly the records",
        "listed below differ from the original dataset, and each differs only in",
        "its `nature_language` value.",
        "",
        "## Complete Change List",
        "",
    ]

    for item in sorted(changes, key=lambda value: value["index_1based"]):
        lines.extend(
            [
                f"### idx={item['index_1based']} - `{item['uid']}`",
                "",
                f"- Change type: `{item['issue_kind']}`",
                "- Modified field: `nature_language`",
                f"- Rule audit after modification: `{item['rule_status']}`",
                "",
                "**Before**",
                "",
                "```text",
                item["original_query"],
                "```",
                "",
                "**After**",
                "",
                "```text",
                item["final_query"],
                "```",
                "",
                "**Reason**",
                "",
                item["reason"],
                "",
            ]
        )

    lines.extend(
        [
            "## Other Modifications",
            "",
            "There are no other dataset modifications. The Markdown file itself is",
            "documentation and is not one of the 1000 UID JSON records.",
            "",
        ]
    )
    return "\n".join(lines)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_machine_report(report_path: Path, report: dict) -> Path:
    configured = report.get("source_report")
    if not isinstance(configured, str) or not configured:
        raise ValueError("human report is missing source_report")
    path = Path(configured)
    if not path.is_absolute():
        path = report_path.parent / path
    return path.resolve()


def validate_inputs(
    *,
    source_dir: Path,
    chinese_dir: Path,
    uid_file: Path,
    report_path: Path,
) -> tuple[list[str], list[dict], dict[str, dict]]:
    report = read_object(report_path)
    changes = report.get("confirmed_changes")
    keep_indices = report.get("keep_original_indices")
    if not isinstance(changes, list) or not isinstance(keep_indices, list):
        raise ValueError("human report must contain change and keep lists")

    change_indices = [item.get("index_1based") for item in changes]
    change_uids = [item.get("uid") for item in changes]
    if len(change_indices) != len(set(change_indices)):
        raise ValueError("human report contains duplicate changed indices")
    if len(change_uids) != len(set(change_uids)):
        raise ValueError("human report contains duplicate changed UIDs")
    if set(change_indices) & set(keep_indices):
        raise ValueError("human report change and keep lists overlap")

    summary = report.get("summary", {})
    if summary.get("confirmed_change") != len(changes):
        raise ValueError("human report confirmed_change count is inconsistent")
    if summary.get("keep_original") != len(keep_indices):
        raise ValueError("human report keep_original count is inconsistent")
    if summary.get("selected") != len(changes) + len(keep_indices):
        raise ValueError("human report selected count is inconsistent")

    uids = [
        line.strip()
        for line in uid_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(uids) != len(set(uids)):
        raise ValueError(f"{uid_file}: duplicate UIDs")

    expected_files = {f"{uid}.json" for uid in uids}
    source_files = {path.name for path in source_dir.glob("*.json")}
    chinese_files = {path.name for path in chinese_dir.glob("*.json")}
    if source_files != expected_files:
        raise ValueError(
            f"{source_dir}: JSON file set does not match the {len(uids)} UID list"
        )
    if chinese_files != expected_files:
        raise ValueError(
            f"{chinese_dir}: JSON file set does not match the {len(uids)} UID list"
        )

    machine_report_path = resolve_machine_report(report_path, report)
    machine_report = read_object(machine_report_path)
    machine_records = machine_report.get("records")
    if not isinstance(machine_records, list):
        raise ValueError(f"{machine_report_path}: records must be a list")
    machine_by_uid = {item.get("uid"): item for item in machine_records}

    for item in changes:
        index = item.get("index_1based")
        uid = item.get("uid")
        translation = item.get("recommended_translation")
        if not isinstance(index, int) or not 1 <= index <= len(uids):
            raise ValueError(f"invalid changed index: {index!r}")
        if uids[index - 1] != uid:
            raise ValueError(
                f"index/UID mismatch at {index}: {uid!r} != {uids[index - 1]!r}"
            )
        if not isinstance(translation, str) or not translation.strip():
            raise ValueError(f"{uid}: recommended_translation is empty")

        source_record = read_object(source_dir / f"{uid}.json")
        if source_record.get("uid") != uid:
            raise ValueError(f"{uid}: source JSON has a different UID")
        machine_record = machine_by_uid.get(uid)
        if machine_record is None:
            raise ValueError(f"{uid}: absent from machine re-audit report")
        if (
            source_record.get("nature_language")
            != machine_record.get("original_english_query")
        ):
            raise ValueError(
                f"{uid}: source query changed after the human review was produced"
            )

    return uids, changes, machine_by_uid


def build_dataset(args: argparse.Namespace) -> dict:
    source_dir = args.source_dir.resolve()
    chinese_dir = args.chinese_dir.resolve()
    uid_file = args.uid_file.resolve()
    output_dir = args.output_dir.resolve()
    report_path = args.report.resolve()
    manifest_path = args.manifest.resolve()

    uids, changes, _ = validate_inputs(
        source_dir=source_dir,
        chinese_dir=chinese_dir,
        uid_file=uid_file,
        report_path=report_path,
    )

    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(
            f"{output_dir} already exists; use --overwrite to replace it"
        )

    temporary_dir = output_dir.with_name(
        f".{output_dir.name}.tmp-{os.getpid()}"
    )
    if temporary_dir.exists():
        raise FileExistsError(f"temporary directory already exists: {temporary_dir}")

    changed_manifest = []
    try:
        shutil.copytree(source_dir, temporary_dir)

        for item in changes:
            index = item["index_1based"]
            uid = item["uid"]
            path = temporary_dir / f"{uid}.json"
            translated = read_object(path)
            original_query = translated["nature_language"]
            translated["nature_language"] = item["recommended_translation"].strip()

            chinese = read_object(chinese_dir / f"{uid}.json")
            rule_result = audit_record(index, uid, chinese, translated)
            if rule_result["status"] == "invalid":
                issue_codes = [issue["code"] for issue in rule_result["issues"]]
                raise ValueError(
                    f"{uid}: recommended translation failed rule audit: {issue_codes}"
                )

            write_object(path, translated)
            changed_manifest.append(
                {
                    "index_1based": index,
                    "uid": uid,
                    "issue_kind": item["issue_kind"],
                    "reason": item["reason"],
                    "rule_status": rule_result["status"],
                    "rule_issue_codes": [
                        issue["code"] for issue in rule_result["issues"]
                    ],
                    "source_file_sha256": sha256_file(
                        source_dir / f"{uid}.json"
                    ),
                    "output_file_sha256": sha256_file(path),
                    "original_query": original_query,
                    "final_query": translated["nature_language"],
                }
            )

        write_text(
            temporary_dir / CHANGELOG_NAME,
            render_change_log(len(uids), changed_manifest),
        )

        output_files = {path.name for path in temporary_dir.glob("*.json")}
        expected_files = {f"{uid}.json" for uid in uids}
        if output_files != expected_files:
            raise ValueError("generated output file set does not match the UID list")

        changed_uids = {item["uid"] for item in changes}
        actual_changed_uids = {
            uid
            for uid in uids
            if sha256_file(source_dir / f"{uid}.json")
            != sha256_file(temporary_dir / f"{uid}.json")
        }
        if actual_changed_uids != changed_uids:
            raise ValueError(
                "generated file differences do not match the adjudicated UID set"
            )

        if output_dir.exists():
            shutil.rmtree(output_dir)
        temporary_dir.replace(output_dir)
    except Exception:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        raise

    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "human_report": str(report_path),
        "uid_file": str(uid_file),
        "total_records": len(uids),
        "changed_records": len(changed_manifest),
        "unchanged_records": len(uids) - len(changed_manifest),
        "change_log": str(output_dir / CHANGELOG_NAME),
        "changes": changed_manifest,
    }
    write_object(manifest_path, manifest)
    return manifest


def main() -> int:
    args = parse_args()
    manifest = build_dataset(args)
    print(f"Output: {manifest['output_dir']}")
    print(f"Records: {manifest['total_records']}")
    print(f"Changed: {manifest['changed_records']}")
    print(f"Unchanged: {manifest['unchanged_records']}")
    print(f"Manifest: {args.manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
