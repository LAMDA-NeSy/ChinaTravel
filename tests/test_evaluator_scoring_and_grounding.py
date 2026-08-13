import contextlib
import io
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import pandas as pd

import eval_tpc
from chinatravel.evaluation import commonsense_constraint as evaluation
from chinatravel.symbol_verification import commonsense_constraint as commonsense


def _preference_plan():
    activities = [
        {"type": "attraction", "transports": []}
        for _ in range(4)
    ]
    activities.extend(
        {"type": meal_type, "transports": []}
        for meal_type in ("breakfast", "lunch", "dinner")
    )
    return {
        "people_number": 1,
        "start_city": "北京",
        "target_city": "南京",
        "itinerary": [{"day": 1, "activities": activities}],
    }


class DefaultPreferenceScoringTests(unittest.TestCase):
    def test_no_innercity_transport_receives_zero_att(self):
        plan = _preference_plan()

        scores = eval_tpc.cal_default_pr_score(
            ["valid"],
            {"valid": {}},
            {"valid": plan},
            ["valid"],
        )

        np.testing.assert_allclose(scores, np.array([1.0, 0.0, 1.0]))

    def test_invalid_samples_contribute_zero_to_preference_average(self):
        plan = _preference_plan()

        scores = eval_tpc.cal_default_pr_score(
            ["valid", "invalid"],
            {"valid": {}, "invalid": {}},
            {"valid": plan, "invalid": plan},
            ["valid"],
        )

        np.testing.assert_allclose(scores, np.array([0.5, 0.0, 0.5]))


class CommonsenseExceptionTests(unittest.TestCase):
    def test_validator_exception_is_recorded_as_failure(self):
        zero_result = pd.DataFrame({"Mock Validation": [0]})
        validator_names = (
            "Is_activity_grounded",
            "Is_intercity_transport_correct",
            "Is_attractions_correct",
            "Is_hotels_correct",
            "Is_restaurants_correct",
            "Is_transport_correct",
            "Is_time_correct",
            "Is_space_correct",
        )

        with ExitStack() as stack:
            stack.enter_context(patch.object(evaluation, "_set_tool_lang"))
            for name in validator_names:
                stack.enter_context(
                    patch.object(
                        evaluation,
                        name,
                        return_value=(zero_result, []),
                    )
                )
            stack.enter_context(
                patch.object(
                    evaluation,
                    "Is_time_correct",
                    side_effect=RuntimeError("test failure"),
                )
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                _, _, result_agg, pass_ids = (
                    evaluation.evaluate_commonsense_constraints(
                        ["query-id"],
                        {
                            "query-id": {
                                "start_city": "北京",
                                "target_city": "南京",
                            }
                        },
                        {"query-id": {"itinerary": []}},
                        lang="zh",
                    )
                )

        self.assertEqual(
            result_agg.loc[0, "Commonsense Evaluator Exception"],
            1,
        )
        self.assertEqual(pass_ids, [])
        self.assertIn("query-id", stderr.getvalue())
        self.assertIn("test failure", stderr.getvalue())


class SamePositionTransportTests(unittest.TestCase):
    def test_unrelated_transport_at_same_position_is_rejected(self):
        plan = {
            "itinerary": [
                {
                    "activities": [
                        {
                            "type": "attraction",
                            "position": "Same Place",
                            "transports": [],
                        },
                        {
                            "type": "attraction",
                            "position": "Same Place",
                            "transports": [
                                {
                                    "start": "Other Place A",
                                    "end": "Other Place B",
                                }
                            ],
                        },
                    ]
                }
            ]
        }

        table, errors = commonsense.Is_space_correct(
            {"target_city": "南京"},
            plan,
        )

        self.assertEqual(
            table.loc[0, "Invalid Transport information across positions"],
            1,
        )
        self.assertTrue(any("same position" in error for error in errors))

    def test_empty_transport_at_same_position_is_accepted(self):
        plan = {
            "itinerary": [
                {
                    "activities": [
                        {
                            "type": "attraction",
                            "position": "Same Place",
                            "transports": [],
                        },
                        {
                            "type": "attraction",
                            "position": "Same Place",
                            "transports": [],
                        },
                    ]
                }
            ]
        }

        table, errors = commonsense.Is_space_correct(
            {"target_city": "南京"},
            plan,
        )

        self.assertEqual(table.loc[0].sum(), 0)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
