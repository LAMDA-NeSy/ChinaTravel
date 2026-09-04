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
from chinatravel.agent.load_model import (
    build_method_name,
    ensure_method_language,
    method_has_language,
)


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

    def test_decorated_method_name_detects_embedded_language_suffix(self):
        method = build_method_name(
            "LLM-modulo",
            "gpt-4.1",
            lang="en",
            refine_steps=10,
            oracle_translation=True,
        )

        self.assertTrue(method_has_language(method, "en"))
        self.assertEqual(ensure_method_language(method, "en"), method)

    def test_language_suffix_is_inserted_before_method_modifiers(self):
        method = "LLM-modulo_gpt-4.1_10steps_oracletranslation"

        self.assertEqual(
            ensure_method_language(method, "en"),
            "LLM-modulo_gpt-4.1_en_10steps_oracletranslation",
        )

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

    def test_no_api_does_not_load_api_config(self):
        dictionary = build_translation_assets.TranslationDictionary()
        source_record = {
            "uid": "offline-query",
            "nature_language": "离线翻译测试",
            "hard_logic_py": [],
        }
        with tempfile.TemporaryDirectory() as temp_name:
            output_dir = Path(temp_name) / "output"
            with (
                patch.object(
                    build_translation_assets,
                    "load_translation_api_config",
                    side_effect=AssertionError("API config must not be loaded"),
                ),
                patch.object(
                    build_translation_assets,
                    "build_dictionary",
                    return_value=dictionary,
                ),
                patch.object(
                    build_translation_assets,
                    "local_records",
                    return_value=[(Path("offline-query.json"), source_record)],
                ),
            ):
                build_translation_assets.main(
                    [
                        "--no-api",
                        "--api-config",
                        str(Path(temp_name) / "missing.json"),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            summary = json.loads(
                (output_dir / "summary.json").read_text(encoding="utf-8")
            )
            failures = json.loads(
                (output_dir / "query_translation_failures.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIsNone(summary["api_config"])
            self.assertEqual(summary["translation_api"], {"enabled": False})
            self.assertEqual(
                failures,
                [{"reason": "API disabled", "uid": "offline-query"}],
            )


if __name__ == "__main__":
    unittest.main()
