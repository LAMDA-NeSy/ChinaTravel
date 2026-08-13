#!/usr/bin/env python3
"""Export a distributable English sandbox with canonical concept labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from chinatravel.environment.concept_labels import (  # noqa: E402
    ENGLISH_CONCEPT_VALUE_ALIASES,
)


SOURCE_DATABASE = PROJECT_ROOT / "chinatravel" / "environment" / "database_en"
DATASET_SPECS = {
    "attraction": {
        "pattern": "attractions/*/attractions.csv",
        "field": "type",
    },
    "restaurant": {
        "pattern": "restaurants/*/restaurants_*.csv",
        "field": "cuisine",
    },
    "accommodation": {
        "pattern": "accommodations/*/accommodations.csv",
        "field": "featurehoteltype",
    },
}
COMPATIBILITY_ONLY_POI_ALIASES = {
    "Bistro Sola": "Sola Bistro",
}
IGNORED_NAMES = {".DS_Store", "__pycache__"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir",
        type=Path,
        help="New release directory. It must not already exist.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=SOURCE_DATABASE,
        help=f"Source database_en directory (default: {SOURCE_DATABASE})",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help="Optional ZIP path. The release directory is stored as its root entry.",
    )
    return parser.parse_args()


def ignored_paths(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORED_NAMES or name.endswith(".pyc")}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def database_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
        and path.name not in IGNORED_NAMES
        and not path.name.endswith(".pyc")
    }


def rewrite_csv(
    path: Path,
    *,
    field: str,
    aliases: dict[str, str],
) -> tuple[int, Counter[tuple[str, str]], dict[tuple[str, str], set[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        if not reader.fieldnames or field not in reader.fieldnames:
            raise ValueError(f"{path}: missing required field {field!r}")
        fieldnames = reader.fieldnames
        rows = list(reader)

    changes: Counter[tuple[str, str]] = Counter()
    cities: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        source_value = row[field]
        lookup_value = source_value.strip()
        canonical_value = aliases.get(lookup_value, lookup_value)
        if canonical_value != source_value:
            pair = (source_value, canonical_value)
            changes[pair] += 1
            cities[pair].add(path.parent.name)
            row[field] = canonical_value

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)
    return len(rows), changes, cities


def validate_csv_pair(
    source_path: Path,
    output_path: Path,
    *,
    field: str,
    aliases: dict[str, str],
) -> int:
    with source_path.open("r", encoding="utf-8-sig", newline="") as source_file:
        source_reader = csv.DictReader(source_file)
        source_rows = list(source_reader)
        source_fields = source_reader.fieldnames
    with output_path.open("r", encoding="utf-8-sig", newline="") as output_file:
        output_reader = csv.DictReader(output_file)
        output_rows = list(output_reader)
        output_fields = output_reader.fieldnames

    if source_fields != output_fields:
        raise ValueError(f"{output_path}: columns changed during export")
    if len(source_rows) != len(output_rows):
        raise ValueError(f"{output_path}: row count changed during export")

    for row_number, (source_row, output_row) in enumerate(
        zip(source_rows, output_rows), start=2
    ):
        expected_value = aliases.get(
            source_row[field].strip(), source_row[field].strip()
        )
        if output_row[field] != expected_value:
            raise ValueError(
                f"{output_path}:{row_number}: expected {field}={expected_value!r}"
            )
        for column in source_fields or []:
            if column != field and source_row[column] != output_row[column]:
                raise ValueError(
                    f"{output_path}:{row_number}: non-target field {column!r} changed"
                )
    return len(output_rows)


def validate_release(source_root: Path, output_database: Path) -> dict[str, object]:
    source_files = database_files(source_root)
    output_files = database_files(output_database)
    if source_files.keys() != output_files.keys():
        missing = sorted(source_files.keys() - output_files.keys())
        extra = sorted(output_files.keys() - source_files.keys())
        raise ValueError(f"database file mismatch; missing={missing}, extra={extra}")

    target_csv_paths: set[str] = set()
    row_counts: dict[str, int] = {}
    residual_aliases: dict[str, list[str]] = {}
    for kind, spec in DATASET_SPECS.items():
        aliases = ENGLISH_CONCEPT_VALUE_ALIASES[kind]
        total_rows = 0
        residual_values: set[str] = set()
        for output_path in sorted(output_database.glob(spec["pattern"])):
            relative_path = output_path.relative_to(output_database).as_posix()
            target_csv_paths.add(relative_path)
            total_rows += validate_csv_pair(
                source_files[relative_path],
                output_path,
                field=spec["field"],
                aliases=aliases,
            )
            with output_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
                for row in csv.DictReader(file_obj):
                    value = row[spec["field"]]
                    if value in aliases:
                        residual_values.add(value)
        row_counts[kind] = total_rows
        residual_aliases[kind] = sorted(residual_values)

    if any(residual_aliases.values()):
        raise ValueError(f"non-canonical aliases remain: {residual_aliases}")

    for relative_path, source_path in source_files.items():
        if relative_path in target_csv_paths:
            continue
        if source_path.read_bytes() != output_files[relative_path].read_bytes():
            raise ValueError(f"non-target file changed: {relative_path}")

    return {
        "status": "passed",
        "database_file_count": len(output_files),
        "row_counts": row_counts,
        "residual_aliases": residual_aliases,
        "non_target_files_byte_identical": True,
    }


def build_fix_entries(
    aggregate_changes: dict[str, Counter[tuple[str, str]]],
    aggregate_cities: dict[str, dict[tuple[str, str], set[str]]],
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for kind, aliases in ENGLISH_CONCEPT_VALUE_ALIASES.items():
        for source_value, canonical_value in aliases.items():
            pair = (source_value, canonical_value)
            entries.append(
                {
                    "kind": kind,
                    "source": source_value,
                    "canonical": canonical_value,
                    "changed_rows": aggregate_changes[kind][pair],
                    "cities": sorted(aggregate_cities[kind].get(pair, set())),
                }
            )
    return entries


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|")


def write_fixes(
    path: Path,
    *,
    fix_entries: list[dict[str, object]],
    validation: dict[str, object],
) -> None:
    changed_rows = sum(int(entry["changed_rows"]) for entry in fix_entries)
    changed_aliases = sum(bool(entry["changed_rows"]) for entry in fix_entries)
    lines = [
        "# ChinaTravel English Sandbox Fixes",
        "",
        "This release is a static export of the English sandbox database with",
        "canonical concept labels. It can replace the original `database_en`",
        "directory without requiring runtime alias normalization.",
        "",
        "## Summary",
        "",
        f"- Canonicalized cells: {changed_rows}",
        f"- Alias rules that matched source data: {changed_aliases}",
        f"- Attraction rows checked: {validation['row_counts']['attraction']}",
        f"- Restaurant rows checked: {validation['row_counts']['restaurant']}",
        f"- Accommodation rows checked: {validation['row_counts']['accommodation']}",
        f"- Database files included: {validation['database_file_count']}",
        "- Non-target fields and non-CSV data are unchanged.",
        "- `.DS_Store` and Python cache files are excluded.",
        "",
        "## Canonicalization Table",
        "",
        "| Dataset | Original value | Canonical value | Changed rows | Cities |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for entry in fix_entries:
        lines.append(
            "| {kind} | `{source}` | `{canonical}` | {rows} | {cities} |".format(
                kind=entry["kind"],
                source=markdown_escape(str(entry["source"])),
                canonical=markdown_escape(str(entry["canonical"])),
                rows=entry["changed_rows"],
                cities=len(entry["cities"]),
            )
        )

    lines.extend(
        [
            "",
            "Rules with zero changed rows are retained as compatibility aliases",
            "for generated DSL, but no matching value existed in this database snapshot.",
            "",
            "## POI Name Compatibility",
            "",
            "The database already stores `Sola Bistro` consistently in both the",
            "Shanghai restaurant table and POI index. The evaluator separately maps",
            "the mistranslated query value `Bistro Sola` to `Sola Bistro`; therefore",
            "this static export does not modify or duplicate that POI row.",
            "",
            "## Validation",
            "",
            "- Source and exported database file lists match after excluding system files.",
            "- All CSV schemas and row counts match the source.",
            "- Only the three documented concept fields changed.",
            "- No configured non-canonical concept label remains.",
            "- Every non-target database file is byte-identical to the source.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_checksums(release_root: Path) -> None:
    checksum_path = release_root / "SHA256SUMS"
    files = sorted(
        path
        for path in release_root.rglob("*")
        if path.is_file() and path != checksum_path
    )
    lines = [
        f"{sha256(path)}  {path.relative_to(release_root).as_posix()}" for path in files
    ]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_archive(release_root: Path, archive_path: Path) -> None:
    archive_path = archive_path.resolve()
    if archive_path.exists():
        raise FileExistsError(f"archive already exists: {archive_path}")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(release_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(release_root.parent))


def export_release(source_root: Path, release_root: Path) -> dict[str, object]:
    source_root = source_root.resolve()
    release_root = release_root.resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"source database does not exist: {source_root}")
    if release_root.exists():
        raise FileExistsError(f"output directory already exists: {release_root}")

    output_database = release_root / "database_en"
    release_root.mkdir(parents=True)
    shutil.copytree(source_root, output_database, ignore=ignored_paths)

    aggregate_changes: dict[str, Counter[tuple[str, str]]] = {}
    aggregate_cities: dict[str, dict[tuple[str, str], set[str]]] = {}
    rewritten_files: dict[str, int] = {}
    for kind, spec in DATASET_SPECS.items():
        kind_changes: Counter[tuple[str, str]] = Counter()
        kind_cities: dict[tuple[str, str], set[str]] = defaultdict(set)
        matching_files = sorted(output_database.glob(spec["pattern"]))
        if not matching_files:
            raise ValueError(f"no files matched {spec['pattern']!r}")
        for path in matching_files:
            _, changes, cities = rewrite_csv(
                path,
                field=spec["field"],
                aliases=ENGLISH_CONCEPT_VALUE_ALIASES[kind],
            )
            kind_changes.update(changes)
            for pair, city_names in cities.items():
                kind_cities[pair].update(city_names)
        aggregate_changes[kind] = kind_changes
        aggregate_cities[kind] = kind_cities
        rewritten_files[kind] = len(matching_files)

    validation = validate_release(source_root, output_database)
    fix_entries = build_fix_entries(aggregate_changes, aggregate_cities)
    manifest = {
        "schema_version": 1,
        "release_name": release_root.name,
        "language": "en",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_database": "chinatravel/environment/database_en",
        "output_database": "database_en",
        "rewritten_files": rewritten_files,
        "changed_rows": sum(int(entry["changed_rows"]) for entry in fix_entries),
        "fixes": fix_entries,
        "compatibility_only_poi_aliases": COMPATIBILITY_ONLY_POI_ALIASES,
        "validation": validation,
    }
    (release_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_fixes(
        release_root / "FIXES.md",
        fix_entries=fix_entries,
        validation=validation,
    )
    write_checksums(release_root)
    return manifest


def main() -> int:
    args = parse_args()
    manifest = export_release(args.source, args.output_dir)
    if args.archive:
        write_archive(args.output_dir.resolve(), args.archive)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if args.archive:
        print(f"archive_sha256={sha256(args.archive.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
