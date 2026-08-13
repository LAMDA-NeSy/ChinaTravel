import copy
import random
import unittest

from synthetic_query_generation.catalog import (
    FAMILIAR_CONSTRAINT_KEYS,
    FULL_CONSTRAINT_KEYS,
    LEGACY_FULL_CONSTRAINT_KEYS,
    NEW_CONSTRAINT_KEYS,
    validate_catalog,
)
from synthetic_query_generation.constraints import (
    choose_constraints,
    make_budget_constraints,
    make_count_constraints,
    make_relation_constraints,
    make_schedule_constraints,
    make_transport_metric_constraints,
)
from synthetic_query_generation.models import (
    ConstraintCandidate,
    ConstraintContext,
    ConstraintGenerationOptions,
    EntityContext,
)
from synthetic_query_generation.templates import TEMPLATE_CATALOG
from synthetic_query_generation.validation import validate_constraints


def _transport(mode, start, end, distance, cost=1):
    transport = {
        "mode": mode,
        "start_time": start,
        "end_time": end,
        "distance": distance,
        "cost": cost,
        "price": cost,
    }
    if mode == "metro":
        transport["tickets"] = 2
    if mode == "taxi":
        transport["cars"] = 1
    return transport


def _plan():
    return {
        "people_number": 2,
        "start_city": "Shanghai",
        "target_city": "Beijing",
        "itinerary": [
            {
                "day": 1,
                "activities": [
                    {
                        "type": "airplane",
                        "start_time": "06:00",
                        "end_time": "08:00",
                        "start": "Shanghai Airport",
                        "end": "Beijing Airport",
                        "tickets": 2,
                        "cost": 1000,
                        "transports": [],
                    },
                    {
                        "type": "breakfast",
                        "position": "Hotel A",
                        "start_time": "08:30",
                        "end_time": "09:00",
                        "cost": 0,
                        "transports": [
                            _transport("taxi", "08:00", "08:25", 12, cost=20)
                        ],
                    },
                    {
                        "type": "attraction",
                        "position": "Museum A",
                        "start_time": "09:30",
                        "end_time": "11:00",
                        "tickets": 2,
                        "cost": 0,
                        "transports": [
                            _transport("walk", "09:00", "09:05", 0.4, cost=0),
                            _transport("metro", "09:05", "09:20", 5, cost=4),
                            _transport("walk", "09:20", "09:30", 0.8, cost=0),
                        ],
                    },
                    {
                        "type": "lunch",
                        "position": "Bistro B",
                        "start_time": "11:20",
                        "end_time": "12:20",
                        "cost": 120,
                        "transports": [
                            _transport("walk", "11:00", "11:20", 1.2, cost=0)
                        ],
                    },
                    {
                        "type": "attraction",
                        "position": "Park C",
                        "start_time": "13:00",
                        "end_time": "14:30",
                        "tickets": 2,
                        "cost": 0,
                        "transports": [
                            _transport("taxi", "12:20", "13:00", 15, cost=25)
                        ],
                    },
                    {
                        "type": "accommodation",
                        "position": "Hotel A",
                        "start_time": "20:00",
                        "end_time": "24:00",
                        "rooms": 1,
                        "room_type": 2,
                        "cost": 500,
                        "transports": [
                            _transport("taxi", "14:30", "15:00", 10, cost=20)
                        ],
                    },
                ],
            },
            {
                "day": 2,
                "activities": [
                    {
                        "type": "breakfast",
                        "position": "Hotel A",
                        "start_time": "08:00",
                        "end_time": "08:30",
                        "cost": 0,
                        "transports": [],
                    },
                    {
                        "type": "attraction",
                        "position": "Gallery D",
                        "start_time": "09:00",
                        "end_time": "10:30",
                        "tickets": 2,
                        "cost": 50,
                        "transports": [
                            _transport("walk", "08:30", "08:35", 0.4, cost=0),
                            _transport("metro", "08:35", "08:50", 4, cost=4),
                            _transport("walk", "08:50", "09:00", 0.8, cost=0),
                        ],
                    },
                    {
                        "type": "dinner",
                        "position": "Restaurant E",
                        "start_time": "17:00",
                        "end_time": "18:00",
                        "cost": 160,
                        "transports": [
                            _transport("taxi", "10:30", "11:00", 8, cost=18)
                        ],
                    },
                    {
                        "type": "train",
                        "start_time": "20:00",
                        "end_time": "22:00",
                        "start": "Beijing Station",
                        "end": "Shanghai Station",
                        "tickets": 2,
                        "cost": 600,
                        "transports": [
                            _transport("walk", "18:00", "18:10", 0.7, cost=0),
                            _transport("metro", "18:10", "18:40", 8, cost=4),
                            _transport("walk", "18:40", "18:50", 0.8, cost=0),
                        ],
                    },
                ],
            },
        ],
    }


def _context(plan=None):
    plan = plan or _plan()
    by_type = {"attraction": [], "restaurant": [], "accommodation": []}
    for day_index, day in enumerate(plan["itinerary"], start=1):
        for activity in day["activities"]:
            activity_type = activity["type"]
            if activity_type == "attraction":
                kind = "attraction"
            elif activity_type in {"breakfast", "lunch", "dinner"}:
                kind = "restaurant"
            elif activity_type == "accommodation":
                kind = "accommodation"
            else:
                continue
            by_type[kind].append(
                {
                    "day": day_index,
                    "activity": activity,
                    "position": activity["position"],
                }
            )
    entities = EntityContext(
        by_type=by_type,
        type_values={"attraction": [], "restaurant": [], "accommodation": []},
    )
    return ConstraintContext(
        plan=plan,
        lang="en",
        rng=random.Random(7),
        options=ConstraintGenerationOptions(),
        entities_loader=lambda: entities,
    )


def _new_candidates(context=None):
    context = context or _context()
    candidates = []
    for factory in (
        make_transport_metric_constraints,
        make_count_constraints,
        make_schedule_constraints,
        make_relation_constraints,
        make_budget_constraints,
    ):
        candidates.extend(factory(context))
    return candidates


def _candidate(candidates, key):
    return next(candidate for candidate in candidates if candidate.key == key)


def test_new_constraint_catalog_and_seed_plan_validation():
    validate_catalog(TEMPLATE_CATALOG)
    assert len(LEGACY_FULL_CONSTRAINT_KEYS) == 39
    assert len(FAMILIAR_CONSTRAINT_KEYS) == 29
    assert FULL_CONSTRAINT_KEYS == LEGACY_FULL_CONSTRAINT_KEYS | NEW_CONSTRAINT_KEYS

    plan = _plan()
    candidates = _new_candidates(_context(plan))
    assert NEW_CONSTRAINT_KEYS <= {candidate.key for candidate in candidates}
    assert all("len(" not in candidate.code for candidate in candidates)

    ok, results = validate_constraints(
        plan,
        [candidate.code for candidate in candidates],
        "en",
    )
    assert ok, [
        candidate.key
        for candidate, result in zip(candidates, results)
        if not result
    ]


def test_new_constraints_fail_after_relevant_plan_mutations():
    plan = _plan()
    candidates = _new_candidates(_context(plan))

    fewer_attractions = copy.deepcopy(plan)
    fewer_attractions["itinerary"][0]["activities"] = [
        activity
        for activity in fewer_attractions["itinerary"][0]["activities"]
        if activity.get("position") != "Park C"
    ]
    assert not validate_constraints(
        fewer_attractions,
        [_candidate(candidates, "total_attraction_count").code],
        "en",
    )[0]

    excessive_walking = copy.deepcopy(plan)
    for day in excessive_walking["itinerary"]:
        for activity in day["activities"]:
            for transport in activity.get("transports", []):
                if transport["mode"] == "walk":
                    transport["distance"] *= 100
    assert not validate_constraints(
        excessive_walking,
        [_candidate(candidates, "walking_distance_budget").code],
        "en",
    )[0]

    reversed_plan = copy.deepcopy(plan)
    all_activities = [
        activity
        for day in reversed_plan["itinerary"]
        for activity in day["activities"]
    ]
    reversed_plan["itinerary"] = [
        {"day": 1, "activities": list(reversed(all_activities))}
    ]
    assert not validate_constraints(
        reversed_plan,
        [_candidate(candidates, "cross_category_order").code],
        "en",
    )[0]

    wrong_intercity_times = copy.deepcopy(plan)
    wrong_intercity_times["itinerary"][0]["activities"][0]["start_time"] = "23:59"
    wrong_intercity_times["itinerary"][1]["activities"][-1]["start_time"] = "00:00"
    assert not validate_constraints(
        wrong_intercity_times,
        [
            _candidate(candidates, "outbound_departure_deadline").code,
            _candidate(candidates, "return_departure_earliest").code,
        ],
        "en",
    )[0]


def test_priority_sampling_reserves_requested_slots():
    candidates = [
        ConstraintCandidate(
            key=f"priority_{index}",
            code="result=True",
            nl={"en": "x"},
            category="test",
        )
        for index in range(4)
    ]
    candidates.extend(
        ConstraintCandidate(
            key=f"ordinary_{index}",
            code="result=True",
            nl={"en": "x"},
            category="test",
            hardness=100,
        )
        for index in range(10)
    )
    priority_keys = {candidate.key for candidate in candidates[:4]}
    selected = choose_constraints(
        candidates,
        random.Random(11),
        count=6,
        min_tricky=0,
        min_logic=0,
        priority_keys=priority_keys,
        min_priority=3,
    )
    assert sum(candidate.key in priority_keys for candidate in selected) >= 3


class SyntheticQueryConstraintTests(unittest.TestCase):
    def test_catalog_and_seed_validation(self):
        test_new_constraint_catalog_and_seed_plan_validation()

    def test_mutations_are_rejected(self):
        test_new_constraints_fail_after_relevant_plan_mutations()

    def test_priority_sampling(self):
        test_priority_sampling_reserves_requested_slots()


if __name__ == "__main__":
    unittest.main()
