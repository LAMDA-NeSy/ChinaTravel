import argparse
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

from agent_env.adapter import ChinaTravelEnvAdapter
from agent_env.scripts.solve_script_with_harness import (
    build_prompt,
    evaluate_one,
    normalize_lang,
    visible_query,
)
from chinatravel.evaluation import preference


class _Rows:
    def to_dict(self, orient):
        if orient != "records":
            raise ValueError(f"Unexpected orient: {orient}")
        return []


class AgentEnvironmentLanguageTests(unittest.TestCase):
    def test_adapter_uses_explicit_language_for_world_environment(self):
        adapter = ChinaTravelEnvAdapter(lang="en")
        world_env = Mock()
        module = types.ModuleType("chinatravel.environment.world_env")
        module.WorldEnv = world_env

        with patch.dict(sys.modules, {module.__name__: module}):
            adapter._get_env()

        world_env.assert_called_once_with(lang="en")

    def test_adapter_uses_environment_language(self):
        with patch.dict(os.environ, {"CHINATRAVEL_LANG": "en"}):
            adapter = ChinaTravelEnvAdapter()

        self.assertEqual(adapter.lang, "en")

    def test_load_query_receives_adapter_language(self):
        adapter = ChinaTravelEnvAdapter(lang="en")
        load_query = Mock(return_value=([], {}))
        module = types.ModuleType("chinatravel.data.load_datasets")
        module.load_query = load_query

        with patch.dict(sys.modules, {module.__name__: module}):
            result = adapter.load_query("easy")

        self.assertTrue(result["success"])
        args = load_query.call_args.args[0]
        self.assertIsInstance(args, argparse.Namespace)
        self.assertEqual(args.lang, "en")

    def test_harness_prompt_uses_matching_cli_language(self):
        prompt = build_prompt(
            "phase1",
            "sample-uid",
            {"uid": "sample-uid", "query": "Plan a trip."},
            "python",
            "en",
        )

        self.assertIn("python -m agent_env.cli --lang en tools", prompt)
        self.assertIn("--lang en call attractions_keys", prompt)

    def test_oracle_fields_are_hidden_from_harness(self):
        public = visible_query(
            {
                "uid": "sample-uid",
                "query": "Plan a trip.",
                "hard_logic": ["secret"],
                "hard_logic_py": ["secret"],
                "hard_logic_nl": ["secret"],
            }
        )

        self.assertEqual(public, {"uid": "sample-uid", "query": "Plan a trip."})

    def test_evaluator_receives_harness_language(self):
        uid = "sample-uid"
        schema_evaluator = Mock(return_value=(1.0, _Rows(), [uid]))
        commonsense_evaluator = Mock(return_value=(1.0, 1.0, _Rows(), [uid]))
        hard_evaluator = Mock(
            return_value=(1.0, 1.0, 1.0, 1.0, _Rows(), [uid])
        )
        modules = {}
        for name in (
            "chinatravel.evaluation.schema_constraint",
            "chinatravel.evaluation.commonsense_constraint",
            "chinatravel.evaluation.hard_constraint",
            "chinatravel.evaluation.utils",
        ):
            modules[name] = types.ModuleType(name)
        modules[
            "chinatravel.evaluation.schema_constraint"
        ].evaluate_schema_constraints = schema_evaluator
        modules[
            "chinatravel.evaluation.commonsense_constraint"
        ].evaluate_commonsense_constraints = commonsense_evaluator
        modules[
            "chinatravel.evaluation.hard_constraint"
        ].evaluate_hard_constraints_v2 = hard_evaluator
        modules["chinatravel.evaluation.utils"].load_json_file = Mock(return_value={})

        with patch.dict(sys.modules, modules):
            result = evaluate_one("phase1", uid, {"uid": uid}, {}, "en")

        self.assertTrue(result["all_pass"])
        self.assertEqual(commonsense_evaluator.call_args.kwargs["lang"], "en")
        self.assertEqual(hard_evaluator.call_args.kwargs["lang"], "en")

    def test_preference_evaluator_infers_english_environment(self):
        uid = "sample-uid"
        query = {
            "start_city": "Beijing",
            "target_city": "Shanghai",
            "preference_py": "max concept\nresult = True",
        }
        set_language = Mock()

        with patch.object(preference, "_set_preference_lang", set_language), patch.object(
            preference,
            "_get_evaluate_preference_py",
            return_value=lambda constraints, plan: [True],
        ):
            result = preference.evaluate_preference_v2(
                [uid], {uid: query}, {uid: {}}, [uid]
            )

        set_language.assert_called_once_with("en")
        self.assertTrue(result.loc[0, "concept"])

    def test_invalid_language_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be 'zh' or 'en'"):
            ChinaTravelEnvAdapter(lang="english")
        with self.assertRaisesRegex(ValueError, "must be 'zh' or 'en'"):
            normalize_lang("english")


if __name__ == "__main__":
    unittest.main()
