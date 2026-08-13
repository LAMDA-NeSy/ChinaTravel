"""Export audited generated records using the phase-one public query schema."""

import argparse
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from synthetic_query_generation.utils import read_json, write_json


RELEASE_FIELDS = (
    "uid",
    "start_city",
    "target_city",
    "days",
    "people_number",
    "hard_logic_py",
    "nature_language",
)


def export_release(dataset_dir, output_dir):
    dataset_dir = Path(dataset_dir)
    source_dir = dataset_dir / "data" if (dataset_dir / "data").is_dir() else dataset_dir
    output_dir = Path(output_dir)
    existing = list(output_dir.glob("*.json")) if output_dir.is_dir() else []
    if existing:
        raise ValueError("Release directory already contains JSON files: {}".format(output_dir))

    paths = sorted(path for path in source_dir.glob("*.json") if path.name != "manifest.json")
    iterator = (
        tqdm(paths, desc="Exporting release", unit="record")
        if tqdm is not None
        else paths
    )
    exported = []
    for path in iterator:
        record = read_json(path)
        missing = [field for field in RELEASE_FIELDS if field not in record]
        if missing:
            raise ValueError("{} misses release fields {}".format(path, missing))
        release_record = {field: record[field] for field in RELEASE_FIELDS}
        if release_record["uid"] != path.stem:
            raise ValueError("{} has a mismatched UID".format(path))
        if not isinstance(release_record["hard_logic_py"], list):
            raise ValueError("{} has a non-list hard_logic_py".format(path))
        write_json(output_dir / path.name, release_record)
        exported.append(release_record["uid"])
    return exported


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-records", type=int, required=True)
    args = parser.parse_args(argv)
    exported = export_release(args.dataset_dir, args.output_dir)
    if len(exported) != args.expected_records:
        raise SystemExit(
            "Expected {} records, exported {}".format(
                args.expected_records, len(exported)
            )
        )
    print("Exported {} records to {}".format(len(exported), args.output_dir))


if __name__ == "__main__":
    main()
