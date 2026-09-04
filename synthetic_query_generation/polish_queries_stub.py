#!/usr/bin/env python3
"""Prepare generated synthetic queries for later LLM polishing.

This script intentionally does not call any LLM API. It either copies generated
records unchanged or writes one prompt file per record. The prompt explicitly
requires preserving the exact constraint semantics.
"""

import argparse
import json
from pathlib import Path


PROMPT_TEMPLATE = """Rewrite the following travel-planning query into fluent {lang_name}.

You must preserve every constraint exactly. Do not add, remove, weaken, or
strengthen any requirement. Keep all city names, POI names, numbers, dates,
times, budgets, room counts, room types, transportation modes, and ordering
constraints unchanged.

Original query:
{nature_language}

Constraint checklist:
{constraints}

Return only the rewritten query.
"""


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def infer_lang(record, fallback):
    if fallback != "auto":
        return fallback
    profile = record.get("generation_profile", {})
    if profile.get("lang") in {"zh", "en"}:
        return profile["lang"]
    text = record.get("nature_language", "")
    if any("\u3400" <= ch <= "\u9fff" for ch in text):
        return "zh"
    return "en"


def prompt_for_record(record, lang):
    lang_name = "Chinese" if lang == "zh" else "English"
    constraints = record.get("hard_logic_nl") or []
    checklist = "\n".join(f"{idx}. {item}" for idx, item in enumerate(constraints, start=1))
    return PROMPT_TEMPLATE.format(
        lang_name=lang_name,
        nature_language=record.get("nature_language", ""),
        constraints=checklist,
    )


def main():
    parser = argparse.ArgumentParser(description="Prepare synthetic query polishing prompts.")
    parser.add_argument("--input-dir", required=True, help="Directory containing generated uid.json records.")
    parser.add_argument("--output-dir", required=True, help="Output directory for copied records or prompts.")
    parser.add_argument("--mode", choices=["copy", "prompts"], default="prompts")
    parser.add_argument("--lang", choices=["auto", "zh", "en"], default="auto")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    records = []
    for path in sorted(input_dir.glob("*.json")):
        record = read_json(path)
        if not isinstance(record, dict) or not record.get("uid"):
            continue
        lang = infer_lang(record, args.lang)
        if args.mode == "copy":
            record = dict(record)
            record.setdefault("polish_status", "not_polished")
            record.setdefault("polish_note", "Copied by polish_queries_stub.py without LLM rewriting.")
            write_json(output_dir / path.name, record)
        else:
            write_text(output_dir / f"{record['uid']}.prompt.txt", prompt_for_record(record, lang))
        records.append(record["uid"])

    write_json(
        output_dir / "manifest.json",
        {
            "mode": args.mode,
            "input_dir": str(input_dir),
            "num_records": len(records),
            "uids": records,
        },
    )
    print(f"Prepared {len(records)} records in {output_dir}")


if __name__ == "__main__":
    main()
