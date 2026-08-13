#!/usr/bin/env python3
"""Export Phase 1 LLM-invalid translations for manual review."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from audit_phase1_translations import (
    PROJECT_ROOT,
    audit_record,
    load_audit_config,
    read_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "translation_api_config.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to <audit.paths.output_dir>/manual_review.",
    )
    return parser.parse_args()


def resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def without_raw_content(data: dict) -> dict:
    return {
        key: value
        for key, value in data.items()
        if key not in {"raw_content", "input_fingerprint"}
    }


def attempt_summary(repair: dict | None) -> str:
    if not repair:
        return ""
    summaries = []
    for attempt in repair.get("attempts", []):
        if attempt.get("error"):
            outcome = f"error={attempt['error']}"
        else:
            validation = attempt.get("validation", {})
            outcome = (
                f"rule={validation.get('rule_status', 'not_run')},"
                f"llm={validation.get('llm_verdict', 'not_run')}"
            )
        summaries.append(f"attempt {attempt.get('attempt')}: {outcome}")
    return " | ".join(summaries)


def markdown_block(value: object, language: str = "text") -> list[str]:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, indent=2)
        language = "json"
    else:
        text = str(value or "")
    return [f"```{language}", text, "```", ""]


def write_failed_markdown(path: Path, failed_records: list[dict]) -> None:
    lines = [
        "# Phase 1 Failed Translation Repairs",
        "",
        f"- Failed records: {len(failed_records)}",
        "- These records remain unchanged in the repaired dataset.",
        "",
    ]
    for record in failed_records:
        repair = record["repair"]
        lines.extend(
            [
                f"## {record['index_1based']}. `{record['uid']}`",
                "",
                "### Chinese Query",
                "",
                *markdown_block(record["chinese_query"]),
                "### Original English Query",
                "",
                *markdown_block(record["original_english_query"]),
                "### Oracle DSL",
                "",
                *markdown_block(record["translated_hard_logic_py"]),
                "### Initial LLM Audit",
                "",
                *markdown_block(record["llm_audit"]),
            ]
        )
        for attempt in repair.get("attempts", []):
            lines.extend(
                [
                    f"### Repair Attempt {attempt.get('attempt')}",
                    "",
                    *markdown_block(attempt),
                ]
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    config = load_audit_config(config_path)
    base_dir = config_path.parent
    paths = config["audit"]["paths"]
    source_dir = resolve_path(paths["source_dir"], base_dir)
    translated_dir = resolve_path(paths["translated_dir"], base_dir)
    uid_file = resolve_path(paths["uid_file"], base_dir)
    audit_dir = resolve_path(paths["output_dir"], base_dir)
    repaired_dir = resolve_path(paths["repaired_dir"], base_dir)
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else audit_dir / "manual_review"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    uids = [
        line.strip()
        for line in uid_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records = []
    for index, uid in enumerate(uids, start=1):
        llm_path = audit_dir / "llm_results" / f"{uid}.json"
        if not llm_path.is_file():
            continue
        llm_audit = read_json(llm_path)
        if llm_audit.get("verdict") != "invalid":
            continue

        source = read_json(source_dir / f"{uid}.json")
        translated = read_json(translated_dir / f"{uid}.json")
        rule_audit = audit_record(index, uid, source, translated)
        repair_path = audit_dir / "repair_results" / f"{uid}.json"
        repair = read_json(repair_path) if repair_path.is_file() else None
        final_path = repaired_dir / f"{uid}.json"
        final_record = read_json(final_path) if final_path.is_file() else translated
        records.append(
            {
                "index_1based": index,
                "uid": uid,
                "metadata": {
                    "start_city_zh": source.get("start_city"),
                    "start_city_en": translated.get("start_city"),
                    "target_city_zh": source.get("target_city"),
                    "target_city_en": translated.get("target_city"),
                    "days": source.get("days"),
                    "people_number": source.get("people_number"),
                },
                "chinese_query": source.get("nature_language", ""),
                "original_english_query": translated.get("nature_language", ""),
                "source_hard_logic_py": source.get("hard_logic_py", []),
                "translated_hard_logic_py": translated.get("hard_logic_py", []),
                "rule_audit": {
                    "status": rule_audit["status"],
                    "issues": rule_audit.get("issues", []),
                },
                "llm_audit": without_raw_content(llm_audit),
                "repair": without_raw_content(repair) if repair else None,
                "final_english_query": final_record.get("nature_language", ""),
                "changed": (
                    final_record.get("nature_language", "")
                    != translated.get("nature_language", "")
                ),
            }
        )

    repair_counts = Counter(
        (record["repair"] or {}).get("status", "not_run") for record in records
    )
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_file": str(config_path),
        "summary": {
            "llm_invalid": len(records),
            "repair_status_counts": dict(sorted(repair_counts.items())),
        },
        "records": records,
    }
    write_json(output_dir / "phase1_llm_invalid_review.json", payload)
    (output_dir / "phase1_llm_invalid_uids.txt").write_text(
        "\n".join(record["uid"] for record in records)
        + ("\n" if records else ""),
        encoding="utf-8",
    )

    csv_fields = [
        "index_1based",
        "uid",
        "rule_status",
        "llm_confidence",
        "repair_status",
        "changed",
        "chinese_query",
        "original_english_query",
        "final_english_query",
        "llm_explanation",
        "llm_missing_or_changed_information",
        "attempt_summary",
    ]
    with (output_dir / "phase1_llm_invalid_review.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=csv_fields)
        writer.writeheader()
        for record in records:
            repair = record["repair"] or {}
            llm_audit = record["llm_audit"]
            writer.writerow(
                {
                    "index_1based": record["index_1based"],
                    "uid": record["uid"],
                    "rule_status": record["rule_audit"]["status"],
                    "llm_confidence": llm_audit.get("confidence"),
                    "repair_status": repair.get("status", "not_run"),
                    "changed": record["changed"],
                    "chinese_query": record["chinese_query"],
                    "original_english_query": record["original_english_query"],
                    "final_english_query": record["final_english_query"],
                    "llm_explanation": llm_audit.get("explanation", ""),
                    "llm_missing_or_changed_information": " | ".join(
                        llm_audit.get("missing_or_changed_information", [])
                    ),
                    "attempt_summary": attempt_summary(record["repair"]),
                }
            )

    failed_records = [
        record
        for record in records
        if (record["repair"] or {}).get("status") == "failed"
    ]
    write_failed_markdown(
        output_dir / "phase1_failed_repairs_review.md",
        failed_records,
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote manual review files to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
