#!/usr/bin/env python3
"""Regression tests for syntax-safe DSL dictionary translation."""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_translation_assets import translate_dsl_code


class TranslationDslTest(unittest.TestCase):
    def test_apostrophes_and_bullets_remain_inside_string_literals(self):
        source_name = "盖碗儿梨园"
        translated_name = (
            "Gaiwan'er Pear Garden • Sichuan Opera Face-Changing Theater"
        )
        source = (
            "result=False\n"
            "for activity in allactivities(plan):\n"
            f"  if activity_position(activity)=='{source_name}':\n"
            "    result=True"
        )

        translated, matched, unresolved = translate_dsl_code(
            source,
            {source_name: translated_name},
        )

        tree = ast.parse(translated, mode="exec")
        string_values = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn(translated_name, string_values)
        self.assertEqual(matched, [source_name])
        self.assertEqual(unresolved, [])

    def test_apostrophe_in_set_literal_is_quoted_safely(self):
        source = "result=({'儿童乐园'}<=accommodation_type_set)"
        translated, _, _ = translate_dsl_code(
            source,
            {"儿童乐园": "Children's Playground"},
        )

        ast.parse(translated, mode="exec")
        self.assertIn("Children's Playground", translated)


if __name__ == "__main__":
    unittest.main()
