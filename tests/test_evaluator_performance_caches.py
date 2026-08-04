import unittest
from unittest.mock import patch

from geopy.distance import geodesic

from chinatravel.environment.tools.transportation import apis
from chinatravel.evaluation import schema_constraint


class TransportationCacheTests(unittest.TestCase):
    def test_nearest_station_matches_geopy_wgs84(self):
        location = (30.7762, 114.2081)
        stations = [
            {"name": "A", "position": (30.7781, 114.2110)},
            {"name": "B", "position": (30.7810, 114.2012)},
        ]
        expected_station = min(
            stations,
            key=lambda station: geodesic(
                location,
                station["position"],
            ).kilometers,
        )
        station, distance = apis.find_nearest_station(
            location,
            stations,
        )

        self.assertEqual(station, expected_station)
        self.assertAlmostEqual(
            distance,
            geodesic(location, station["position"]).kilometers,
            places=12,
        )

    def test_nearest_metro_station_is_cached_per_poi(self):
        transportation = apis.Transportation.__new__(apis.Transportation)
        transportation._nearest_station_cache = {}
        transportation.city_stations_dict = {
            "wuhan": [
                {"name": "A", "position": (30.7781, 114.2110)},
                {"name": "B", "position": (30.7810, 114.2012)},
            ]
        }
        original = apis.find_nearest_station

        with patch.object(
            apis,
            "find_nearest_station",
            wraps=original,
        ) as find_nearest:
            first = transportation._find_nearest_station(
                "wuhan",
                "Wuhan Tianhe International Airport",
                (30.7762, 114.2081),
            )
            second = transportation._find_nearest_station(
                "wuhan",
                "Wuhan Tianhe International Airport",
                (30.7762, 114.2081),
            )

        self.assertEqual(find_nearest.call_count, 1)
        self.assertEqual(first, second)


class SchemaValidatorReuseTests(unittest.TestCase):
    def test_schema_is_compiled_once_per_batch(self):
        schema = {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "integer"}},
        }
        records = {
            "valid": {"value": 1},
            "invalid": {"value": "not-an-integer"},
        }
        original = schema_constraint.validator_for

        with patch.object(
            schema_constraint,
            "validator_for",
            wraps=original,
        ) as get_validator:
            rate, _, pass_ids = (
                schema_constraint.evaluate_schema_constraints(
                    ["valid", "invalid"],
                    records,
                    schema,
                )
            )

        self.assertEqual(get_validator.call_count, 1)
        self.assertEqual(rate, 50.0)
        self.assertEqual(pass_ids, ["valid"])


if __name__ == "__main__":
    unittest.main()
