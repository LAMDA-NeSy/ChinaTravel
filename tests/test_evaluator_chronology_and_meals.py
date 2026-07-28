import unittest
from unittest.mock import patch

import pandas as pd

from chinatravel.symbol_verification import commonsense_constraint as commonsense


class _StaticSelector:
    def __init__(self, rows):
        self._frame = pd.DataFrame(rows)

    def select(self, *args, **kwargs):
        return self._frame.copy()


def _activity(start_time, end_time, transports=None):
    return {
        "type": "attraction",
        "start_time": start_time,
        "end_time": end_time,
        "transports": transports or [],
    }


def _hotel_breakfast(start_time, end_time):
    return {
        "type": "breakfast",
        "position": "Test Hotel",
        "price": 0,
        "cost": 0,
        "start_time": start_time,
        "end_time": end_time,
        "transports": [],
    }


class TimeValidationTests(unittest.TestCase):
    def test_overlapping_activities_are_rejected(self):
        plan = {
            "itinerary": [
                {
                    "activities": [
                        _activity("09:00", "11:00"),
                        _activity("10:00", "12:00"),
                    ]
                }
            ]
        }

        table, errors = commonsense.Is_time_correct({"target_city": "南京"}, plan)

        self.assertEqual(table.loc[0, "Does not follow Chronological Order"], 1)
        self.assertTrue(any("must not overlap" in error for error in errors))

    def test_transport_cannot_depart_before_previous_activity_ends(self):
        inbound_transport = [
            {
                "start_time": "09:30",
                "end_time": "10:30",
            }
        ]
        plan = {
            "itinerary": [
                {
                    "activities": [
                        _activity("09:00", "10:00"),
                        _activity("10:30", "11:30", inbound_transport),
                    ]
                }
            ]
        }

        table, errors = commonsense.Is_time_correct({"target_city": "南京"}, plan)

        self.assertEqual(table.loc[0, "Does not follow Chronological Order"], 1)
        self.assertTrue(any("Transport must depart" in error for error in errors))

    def test_ordered_activity_and_transport_are_accepted(self):
        inbound_transport = [
            {
                "start_time": "10:00",
                "end_time": "10:30",
            }
        ]
        plan = {
            "itinerary": [
                {
                    "activities": [
                        _activity("09:00", "10:00"),
                        _activity("10:30", "11:30", inbound_transport),
                    ]
                }
            ]
        }

        table, errors = commonsense.Is_time_correct({"target_city": "南京"}, plan)

        self.assertEqual(table.loc[0].sum(), 0)
        self.assertEqual(errors, [])


class MealValidationTests(unittest.TestCase):
    def setUp(self):
        self.symbolic_input = {"target_city": "南京", "people_number": 1}
        self.restaurant_selector = _StaticSelector([])
        self.hotel_selector = _StaticSelector([{"name": "Test Hotel"}])

    def _evaluate(self, plan):
        with (
            patch.object(commonsense, "restaurants", self.restaurant_selector),
            patch.object(commonsense, "accommodation", self.hotel_selector),
        ):
            return commonsense.Is_restaurants_correct(self.symbolic_input, plan)

    def test_one_hotel_breakfast_per_day_is_accepted(self):
        plan = {
            "itinerary": [
                {"activities": [_hotel_breakfast("06:30", "07:30")]},
                {"activities": [_hotel_breakfast("07:00", "08:00")]},
            ]
        }

        table, errors = self._evaluate(plan)

        self.assertEqual(table.loc[0].sum(), 0)
        self.assertEqual(errors, [])

    def test_multiple_hotel_breakfasts_on_one_day_are_rejected(self):
        plan = {
            "itinerary": [
                {
                    "activities": [
                        _hotel_breakfast("06:30", "07:00"),
                        _hotel_breakfast("07:00", "07:30"),
                    ]
                }
            ]
        }

        table, errors = self._evaluate(plan)

        self.assertEqual(table.loc[0, "Repeated Meal Types in One Day"], 1)
        self.assertTrue(any("Only one breakfast" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
