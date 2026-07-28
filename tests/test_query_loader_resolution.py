import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from chinatravel.data import load_datasets


def write_query(path, uid, marker):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "uid": uid,
                "hard_logic_py": [],
                "nature_language": marker,
            }
        ),
        encoding="utf-8",
    )


class LocalQueryResolutionTests(unittest.TestCase):
    def make_root(self, temp_name, split, uids):
        root = Path(temp_name)
        split_file = (
            root
            / "chinatravel"
            / "evaluation"
            / "default_splits"
            / f"{split}.txt"
        )
        split_file.parent.mkdir(parents=True, exist_ok=True)
        split_file.write_text("\n".join(uids) + "\n", encoding="utf-8")
        return root

    def test_named_english_split_cannot_be_shadowed_by_other_directories(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = self.make_root(temp_name, "phase", ["uid-1"])
            data_root = root / "chinatravel" / "data" / "en"
            write_query(data_root / "phase_EN" / "uid-1.json", "uid-1", "official")
            write_query(data_root / "other" / "uid-1.json", "uid-1", "shadow")
            args = SimpleNamespace(splits="phase", lang="en")

            with patch.object(load_datasets, "project_root_path", str(root)):
                query_ids, records = load_datasets.load_query_local(args)

            self.assertEqual(query_ids, ["uid-1"])
            self.assertEqual(records["uid-1"]["nature_language"], "official")

    def test_fallback_resolution_rejects_duplicate_uids(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = self.make_root(temp_name, "combined", ["uid-1"])
            data_root = root / "chinatravel" / "data" / "en"
            write_query(data_root / "first" / "uid-1.json", "uid-1", "first")
            write_query(data_root / "second" / "uid-1.json", "uid-1", "second")
            args = SimpleNamespace(splits="combined", lang="en")

            with patch.object(load_datasets, "project_root_path", str(root)):
                with self.assertRaisesRegex(ValueError, "ambiguous"):
                    load_datasets.load_query_local(args)

    def test_incomplete_named_split_fails_instead_of_mixing_directories(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = self.make_root(temp_name, "phase", ["uid-1", "uid-2"])
            data_root = root / "chinatravel" / "data" / "en"
            write_query(data_root / "phase_EN" / "uid-1.json", "uid-1", "official")
            write_query(data_root / "other" / "uid-2.json", "uid-2", "shadow")
            args = SimpleNamespace(splits="phase", lang="en")

            with patch.object(load_datasets, "project_root_path", str(root)):
                with self.assertRaisesRegex(ValueError, "every configured UID"):
                    load_datasets.load_query_local(args)


if __name__ == "__main__":
    unittest.main()
