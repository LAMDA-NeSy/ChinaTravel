#!/usr/bin/env python3
"""Regression tests for runtime naming and translation configuration paths."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_translation_assets
from chinatravel.agent.load_model import build_method_name


def write_api_config(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "api": {
                    "base_url": "https://example.invalid/v1",
                    "api_key_required": False,
                },
                "translation": {"model": "test-model"},
            }
        ),
        encoding="utf-8",
    )


class RuntimeConfigurationTests(unittest.TestCase):
    def test_rule_nesy_method_name_contains_llm_once(self):
        self.assertEqual(build_method_name("RuleNeSy", "rule"), "RuleNeSy_rule")

    def test_translation_api_config_expands_user_directory(self):
        with tempfile.TemporaryDirectory() as temp_name:
            config_path = Path(temp_name) / "config.json"
            write_api_config(config_path)

            with patch.dict(os.environ, {"HOME": temp_name}):
                loaded_path, config = (
                    build_translation_assets.load_translation_api_config(
                        "~/config.json"
                    )
                )

            self.assertEqual(loaded_path, config_path.resolve())
            self.assertEqual(config["model"], "test-model")

    def test_translation_api_config_keeps_project_relative_paths(self):
        with tempfile.TemporaryDirectory() as temp_name:
            project_root = Path(temp_name)
            config_path = project_root / "configs" / "translation.json"
            write_api_config(config_path)

            with patch.object(
                build_translation_assets, "PROJECT_ROOT", project_root
            ):
                loaded_path, _ = (
                    build_translation_assets.load_translation_api_config(
                        "configs/translation.json"
                    )
                )

            self.assertEqual(loaded_path, config_path.resolve())


if __name__ == "__main__":
    unittest.main()
