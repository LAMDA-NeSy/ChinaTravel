#!/usr/bin/env python3
"""Build a Hugging Face release of the bilingual ChinaTravel sandbox."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CHINESE_SOURCE = PROJECT_ROOT / "chinatravel/environment/database"
DEFAULT_ENGLISH_SOURCE = PROJECT_ROOT / "chinatravel/environment/database_en"
IGNORED_NAMES = {".DS_Store", "__pycache__"}
CITY_TRANSLATIONS = {
    "北京": "Beijing",
    "上海": "Shanghai",
    "南京": "Nanjing",
    "苏州": "Suzhou",
    "杭州": "Hangzhou",
    "深圳": "Shenzhen",
    "成都": "Chengdu",
    "武汉": "Wuhan",
    "广州": "Guangzhou",
    "重庆": "Chongqing",
}
TABLE_NAMES = (
    "attractions",
    "restaurants",
    "accommodations",
    "trains",
    "flights",
    "poi",
    "subway_stations",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir",
        type=Path,
        help="New release directory. It must not already exist.",
    )
    parser.add_argument(
        "--chinese-source",
        type=Path,
        default=DEFAULT_CHINESE_SOURCE,
        help="Chinese database directory.",
    )
    parser.add_argument(
        "--english-source",
        type=Path,
        default=DEFAULT_ENGLISH_SOURCE,
        help="Canonicalized English database directory.",
    )
    parser.add_argument(
        "--english-metadata-dir",
        type=Path,
        help="Optional directory containing FIXES.md and manifest.json.",
    )
    parser.add_argument(
        "--release-version",
        default="2026.08",
        help="Version recorded in the release manifest and data card.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_release_file(path: Path) -> bool:
    return (
        path.is_file()
        and path.name not in IGNORED_NAMES
        and not path.name.endswith((".pyc", ".pyo"))
    )


def source_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if is_release_file(path)
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_source_checksums(root: Path, output_path: Path) -> None:
    lines = [
        f"{sha256(path)}  {relative}"
        for relative, path in source_files(root).items()
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_deterministic_zip(root: Path, output_path: Path, archive_root: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for relative, path in source_files(root).items():
            info = zipfile.ZipInfo(
                f"{archive_root}/{relative}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)


def city_value(city_slug: str, lang: str) -> str:
    if lang == "en":
        return city_slug.title()
    reverse = {value.lower(): key for key, value in CITY_TRANSLATIONS.items()}
    try:
        return reverse[city_slug.lower()]
    except KeyError as exc:
        raise ValueError(f"unknown city slug: {city_slug}") from exc


def read_csv_table(root: Path, lang: str, pattern: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(root.glob(pattern)):
        frame = pd.read_csv(path, encoding="utf-8-sig")
        frame.insert(0, "city", city_value(path.parent.name, lang))
        frame.insert(0, "language", lang)
        frames.append(frame)
    if not frames:
        raise ValueError(f"no CSV files matched {pattern!r} under {root}")
    return pd.concat(frames, ignore_index=True)


def read_train_table(root: Path, lang: str) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for path in sorted((root / "intercity_transport/train").glob("*.json")):
        stem = path.stem
        if not stem.startswith("from_") or "_to_" not in stem:
            raise ValueError(f"unexpected train route filename: {path.name}")
        origin, destination = stem[len("from_") :].split("_to_", 1)
        if lang == "en":
            origin = CITY_TRANSLATIONS.get(origin, origin)
            destination = CITY_TRANSLATIONS.get(destination, destination)
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, list):
            raise ValueError(f"train route is not a JSON list: {path}")
        for value in values:
            records.append(
                {
                    "language": lang,
                    "route_origin_city": origin,
                    "route_destination_city": destination,
                    **value,
                }
            )
    return pd.DataFrame(records)


def read_flight_table(root: Path, lang: str) -> pd.DataFrame:
    path = root / "intercity_transport/airplane.jsonl"
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        records.append({"language": lang, **value})
    return pd.DataFrame(records)


def read_poi_table(root: Path, lang: str) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for path in sorted((root / "poi").glob("*/poi.json")):
        city = city_value(path.parent.name, lang)
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, list):
            raise ValueError(f"POI index is not a JSON list: {path}")
        for value in values:
            position = value.get("position")
            if not isinstance(position, list) or len(position) != 2:
                raise ValueError(f"invalid POI position in {path}: {position!r}")
            records.append(
                {
                    "language": lang,
                    "city": city,
                    "name": value.get("name"),
                    "lat": position[0],
                    "lon": position[1],
                }
            )
    return pd.DataFrame(records)


def read_subway_table(root: Path, lang: str) -> pd.DataFrame:
    path = root / "transportation/subways.json"
    values = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        raise ValueError(f"subway data is not a JSON object: {path}")
    records: list[dict[str, object]] = []
    for city_slug, lines in values.items():
        city = city_value(city_slug, lang)
        for line in lines:
            for station in line.get("stations", []):
                raw_position = str(station.get("position", ""))
                try:
                    lon, lat = (float(part) for part in raw_position.split(",", 1))
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"invalid subway position {raw_position!r} in {path}"
                    ) from exc
                records.append(
                    {
                        "language": lang,
                        "city": city,
                        "line_name": line.get("name"),
                        "station_name": station.get("name"),
                        "lat": lat,
                        "lon": lon,
                    }
                )
    return pd.DataFrame(records)


def build_tables(root: Path, lang: str) -> dict[str, pd.DataFrame]:
    return {
        "attractions": read_csv_table(root, lang, "attractions/*/attractions.csv"),
        "restaurants": read_csv_table(
            root, lang, "restaurants/*/restaurants_*.csv"
        ),
        "accommodations": read_csv_table(
            root, lang, "accommodations/*/accommodations.csv"
        ),
        "trains": read_train_table(root, lang),
        "flights": read_flight_table(root, lang),
        "poi": read_poi_table(root, lang),
        "subway_stations": read_subway_table(root, lang),
    }


def validate_parallel_sources(chinese_root: Path, english_root: Path) -> None:
    chinese = source_files(chinese_root)
    english = source_files(english_root)
    if chinese.keys() != english.keys():
        missing = sorted(chinese.keys() - english.keys())
        extra = sorted(english.keys() - chinese.keys())
        raise ValueError(
            f"Chinese/English source file mismatch; missing={missing}, extra={extra}"
        )


def validate_canonical_english(root: Path) -> None:
    from chinatravel.environment.concept_labels import ENGLISH_CONCEPT_VALUE_ALIASES

    specs = {
        "attraction": ("attractions/*/attractions.csv", "type"),
        "restaurant": ("restaurants/*/restaurants_*.csv", "cuisine"),
        "accommodation": (
            "accommodations/*/accommodations.csv",
            "featurehoteltype",
        ),
    }
    residual: dict[str, list[str]] = {}
    for kind, (pattern, field) in specs.items():
        aliases = ENGLISH_CONCEPT_VALUE_ALIASES[kind]
        values: set[str] = set()
        for path in root.glob(pattern):
            with path.open(encoding="utf-8-sig", newline="") as file_obj:
                for row in csv.DictReader(file_obj):
                    value = str(row.get(field, "")).strip()
                    if value in aliases:
                        values.add(value)
        residual[kind] = sorted(values)
    if any(residual.values()):
        raise ValueError(f"non-canonical English concept labels remain: {residual}")


def write_parquet_tables(
    output_dir: Path,
    tables_by_language: dict[str, dict[str, pd.DataFrame]],
) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for lang, tables in tables_by_language.items():
        counts[lang] = {}
        for name, frame in tables.items():
            path = output_dir / "data" / lang / f"{name}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, index=False, compression="zstd")
            persisted = pd.read_parquet(path)
            if len(persisted) != len(frame):
                raise ValueError(f"Parquet row count mismatch: {path}")
            counts[lang][name] = len(frame)
    if counts["zh"] != counts["en"]:
        raise ValueError(f"Chinese/English table counts differ: {counts}")
    return counts


def dataset_card(version: str, counts: dict[str, dict[str, int]]) -> str:
    config_lines: list[str] = []
    for table in TABLE_NAMES:
        config_lines.extend(
            [
                f"- config_name: {table}",
                "  data_files:",
                "  - split: zh",
                f"    path: data/zh/{table}.parquet",
                "  - split: en",
                f"    path: data/en/{table}.parquet",
            ]
        )
    count_lines = "\n".join(
        f"| `{table}` | {counts['zh'][table]} | {counts['en'][table]} |"
        for table in TABLE_NAMES
    )
    return f"""---
license: cc-by-nc-sa-4.0
language:
- zh
- en
tags:
- travel-planning
- language-agents
- benchmark
configs:
{chr(10).join(config_lines)}
---

# ChinaTravel Sandbox Environment Database

[English](#english) | [简体中文](#简体中文)

Release version: `{version}`

## English

This dataset contains the bilingual static sandbox used by
[ChinaTravel](https://github.com/LAMDA-NeSy/ChinaTravel). It is a companion to
the [ChinaTravel query dataset](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel)
and an artifact of the
[ChinaTravel paper](https://huggingface.co/papers/2412.13682).

The raw ZIP snapshots preserve the exact directory layout expected by the
ChinaTravel evaluator. Viewer-friendly Parquet configs provide normalized
tables for exploration and analysis. The raw snapshots remain the source of
truth for benchmark execution.

### Load normalized tables

```python
from datasets import load_dataset

attractions_en = load_dataset(
    "LAMDA-NeSy/ChinaTravel-Sandbox",
    "attractions",
    split="en",
)
trains_zh = load_dataset(
    "LAMDA-NeSy/ChinaTravel-Sandbox",
    "trains",
    split="zh",
)
```

### Table sizes

| Config | Chinese rows | English rows |
| --- | ---: | ---: |
{count_lines}

### Use with ChinaTravel

Download and extract one raw archive:

- `raw/ChinaTravel_sandbox_zh.zip` contains `database/`.
- `raw/ChinaTravel_sandbox_en.zip` contains `database_en/`.

Place the extracted directory under `chinatravel/environment/`. The English
snapshot uses canonical concept labels. Its exact changes are documented in
`manifests/ENGLISH_FIXES.md` and `manifests/english_manifest.json`.

Per-source-file checksums and a release manifest are included under
`manifests/` and at the repository root.

## 简体中文

本数据集包含 ChinaTravel 使用的中英文静态沙盒，是
[ChinaTravel Query 数据集](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel)
的配套资源，也是
[ChinaTravel 论文](https://huggingface.co/papers/2412.13682)的关联产物。

`raw/` 中的 ZIP 保留测评代码所需的原始目录结构，是正式运行基准时的权威数据；
Parquet config 用于 Hub viewer、检索和统计分析。

```python
from datasets import load_dataset

restaurants_zh = load_dataset(
    "LAMDA-NeSy/ChinaTravel-Sandbox",
    "restaurants",
    split="zh",
)
poi_en = load_dataset(
    "LAMDA-NeSy/ChinaTravel-Sandbox",
    "poi",
    split="en",
)
```

解压中文包后得到 `database/`，解压英文包后得到 `database_en/`，将对应目录放到
`chinatravel/environment/` 即可。英文版本已统一概念标签，具体修改和校验信息见
`manifests/`。

## Citation

```bibtex
@inproceedings{{shao2026chinatravel,
  title     = {{ChinaTravel: An Open-Ended Travel Planning Benchmark with Compositional Constraint Validation for Language Agents}},
  author    = {{Jie-Jing Shao and Bo-Wen Zhang and Xiao-Wen Yang and Baizhi Chen and Siyu Han and Pang Jinghao and Wen-Da Wei and Guohao Cai and Zhenhua Dong and Lan-Zhe Guo and Yu-Feng Li}},
  booktitle = {{The Fourteenth International Conference on Learning Representations}},
  year      = {{2026}},
  url       = {{https://openreview.net/forum?id=0YRVlxY9BH}}
}}
```
"""


def copy_english_metadata(source: Path | None, output_dir: Path) -> None:
    if source is None:
        return
    mappings = {
        "FIXES.md": "ENGLISH_FIXES.md",
        "manifest.json": "english_manifest.json",
    }
    for source_name, output_name in mappings.items():
        path = source / source_name
        if not path.is_file():
            raise FileNotFoundError(f"missing English release metadata: {path}")
        shutil.copy2(path, output_dir / "manifests" / output_name)


def build_release(
    *,
    chinese_root: Path,
    english_root: Path,
    output_dir: Path,
    english_metadata_dir: Path | None,
    release_version: str,
) -> dict[str, object]:
    chinese_root = chinese_root.resolve()
    english_root = english_root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    if not chinese_root.is_dir() or not english_root.is_dir():
        raise FileNotFoundError("both Chinese and English source directories are required")

    validate_parallel_sources(chinese_root, english_root)
    validate_canonical_english(english_root)
    output_dir.mkdir(parents=True)

    tables = {
        "zh": build_tables(chinese_root, "zh"),
        "en": build_tables(english_root, "en"),
    }
    counts = write_parquet_tables(output_dir, tables)

    raw_dir = output_dir / "raw"
    write_deterministic_zip(
        chinese_root,
        raw_dir / "ChinaTravel_sandbox_zh.zip",
        "database",
    )
    write_deterministic_zip(
        english_root,
        raw_dir / "ChinaTravel_sandbox_en.zip",
        "database_en",
    )

    manifests = output_dir / "manifests"
    write_source_checksums(chinese_root, manifests / "SHA256SUMS.zh")
    write_source_checksums(english_root, manifests / "SHA256SUMS.en")
    copy_english_metadata(english_metadata_dir, output_dir)

    (output_dir / "README.md").write_text(
        dataset_card(release_version, counts), encoding="utf-8"
    )

    files = {
        path.relative_to(output_dir).as_posix(): {
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "release_manifest.json"
    }
    manifest: dict[str, object] = {
        "schema_version": 1,
        "release_version": release_version,
        "languages": ["zh", "en"],
        "source_file_count": {
            "zh": len(source_files(chinese_root)),
            "en": len(source_files(english_root)),
        },
        "table_row_counts": counts,
        "raw_archives": {
            "zh": "raw/ChinaTravel_sandbox_zh.zip",
            "en": "raw/ChinaTravel_sandbox_en.zip",
        },
        "validation": {
            "parallel_source_layout": "passed",
            "canonical_english_concepts": "passed",
            "parquet_roundtrip": "passed",
            "bilingual_row_counts": "passed",
        },
        "files": files,
    }
    write_json(output_dir / "release_manifest.json", manifest)
    return manifest


def main() -> int:
    args = parse_args()
    manifest = build_release(
        chinese_root=args.chinese_source,
        english_root=args.english_source,
        output_dir=args.output_dir,
        english_metadata_dir=args.english_metadata_dir,
        release_version=args.release_version,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
