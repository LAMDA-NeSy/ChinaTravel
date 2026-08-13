import unittest

from chinatravel.environment.concept_labels import (
    ENGLISH_CONCEPT_VALUE_ALIASES,
    normalize_concept_value as normalize_sandbox_concept_value,
)
from chinatravel.environment.tools.accommodations.apis import Accommodations
from chinatravel.environment.tools.attractions.apis import Attractions
from chinatravel.environment.tools.restaurants.apis import Restaurants
from chinatravel.symbol_verification.concept_func import (
    innercity_transport_cost,
    innercity_transport_distance,
    innercity_transport_time,
    normalize_concept_constraint_source,
    normalize_concept_value,
    set_concept_func_lang,
)
from chinatravel.symbol_verification.hard_constraint import evaluate_constraints_py


class ConceptNormalizationTests(unittest.TestCase):
    def tearDown(self):
        set_concept_func_lang("zh")

    def test_symbolic_and_sandbox_normalization_share_aliases(self):
        set_concept_func_lang("en")

        self.assertEqual(normalize_concept_value("restaurant", "cafe"), "coffee shop")
        self.assertEqual(
            normalize_sandbox_concept_value(
                "attraction", "university campus", "en"
            ),
            "University campus",
        )
        self.assertEqual(
            normalize_sandbox_concept_value("accommodation", "Swimming pool", "zh"),
            "Swimming pool",
        )

    def test_constraint_literals_use_the_shared_alias_dictionary(self):
        source = (
            'result=({"cafe", "university campus", "Swimming pool"} '
            "<= concept_values)"
        )
        normalized = normalize_concept_constraint_source(source)

        self.assertIn('"coffee shop"', normalized)
        self.assertIn('"University campus"', normalized)
        self.assertIn('"Swimming Pool"', normalized)

    def test_english_environment_exposes_only_canonical_values(self):
        cases = (
            (Attractions(lang="en"), "type", "attraction"),
            (Restaurants(lang="en"), "cuisine", "restaurant"),
            (Accommodations(lang="en"), "featurehoteltype", "accommodation"),
        )

        for tool, column, kind in cases:
            aliases = ENGLISH_CONCEPT_VALUE_ALIASES[kind]
            with self.subTest(kind=kind):
                for table in tool.data.values():
                    values = set(table[column].dropna())
                    self.assertTrue(values.isdisjoint(aliases))
                    self.assertEqual(
                        values,
                        {
                            normalize_sandbox_concept_value(kind, value, "en")
                            for value in values
                        },
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
