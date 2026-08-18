import unittest

from chinatravel.environment.concept_labels import (
    LEGACY_ENGLISH_CONCEPT_VALUE_ALIASES,
)
from chinatravel.environment.tools.accommodations.apis import Accommodations
from chinatravel.environment.tools.attractions.apis import Attractions
from chinatravel.environment.tools.restaurants.apis import Restaurants
from chinatravel.symbol_verification.concept_func import (
    activity_position,
    innercity_transport_cost,
    innercity_transport_distance,
    innercity_transport_time,
)
from chinatravel.symbol_verification.hard_constraint import evaluate_constraints_py


class CanonicalSandboxContractTests(unittest.TestCase):
    def test_installed_english_sandbox_contains_no_legacy_concept_labels(self):
        cases = (
            (Attractions(lang="en"), "type", "attraction"),
            (Restaurants(lang="en"), "cuisine", "restaurant"),
            (Accommodations(lang="en"), "featurehoteltype", "accommodation"),
        )

        for tool, column, kind in cases:
            legacy_values = set(LEGACY_ENGLISH_CONCEPT_VALUE_ALIASES[kind])
            with self.subTest(kind=kind):
                for table in tool.data.values():
                    values = set(table[column].dropna())
                    self.assertTrue(values.isdisjoint(legacy_values))

    def test_poi_names_are_not_rewritten_at_runtime(self):
        activity = {"type": "lunch", "position": "Bistro Sola"}
        self.assertEqual(activity_position(activity), "Bistro Sola")

    def test_legacy_concept_literals_are_not_rewritten_at_runtime(self):
        plan = {"itinerary": [], "people_number": 1}
        self.assertEqual(
            evaluate_constraints_py(['result=("cafe"=="coffee shop")'], plan),
            [False],
        )


class InnerCityTransportHelperTests(unittest.TestCase):
    def test_mode_filters_support_current_and_legacy_transport_fields(self):
        transports = [
            {
                "mode": "walk",
                "cost": 1,
                "distance": 1.5,
                "start_time": "08:00",
                "end_time": "08:10",
            },
            {
                "type": "walk",
                "cost": 2,
                "distance": 2.5,
                "start_time": "08:10",
                "end_time": "08:15",
            },
            {
                "mode": "taxi",
                "cost": 9,
                "distance": 8,
                "start_time": "08:15",
                "end_time": "08:30",
            },
        ]

        self.assertEqual(innercity_transport_cost(transports, "walk"), 3)
        self.assertEqual(innercity_transport_distance(transports, "walk"), 4)
        self.assertEqual(innercity_transport_time(transports, "walk"), 15)
        self.assertEqual(innercity_transport_cost(transports), 12)
        self.assertEqual(innercity_transport_distance(transports), 12)
        self.assertEqual(innercity_transport_time(transports), 30)


class LegacyHardLogicNormalizationTests(unittest.TestCase):
    def test_apostrophe_and_middle_dot_in_poi_name_are_executable(self):
        poi_name = "Comrade Mao Zedong's Former Residence·Main Hall"
        constraint = f"""
result = False
for activity in allactivities(plan):
    if activity_position(activity) == '{poi_name}':
        result = True
"""
        plan = {
            "itinerary": [
                {
                    "day": 1,
                    "activities": [
                        {"type": "attraction", "position": poi_name, "transports": []}
                    ],
                }
            ]
        }

        self.assertEqual(evaluate_constraints_py([constraint], plan), [True])


if __name__ == "__main__":
    unittest.main()
