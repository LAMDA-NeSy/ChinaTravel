#!/usr/bin/env python3
"""Generate verified synthetic ChinaTravel query records from seed plans.

The intended workflow is:

1. Generate unconstrained seed queries with the ``seed-queries`` subcommand.
2. Run a planner, such as UrbanTrip, on those seed queries to obtain valid plans.
3. Run the ``from-plans`` subcommand to sample constraints that are guaranteed
   to be satisfied by each seed plan.

The generated records keep strict ``hard_logic_py`` constraints and templated
natural language. A separate polishing script can rewrite the natural language
later, but it must preserve the generated constraints.
"""

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from chinatravel.environment.language import CITY_NAMES, normalize_lang
from chinatravel.symbol_verification.concept_func import (
    accommodation_type,
    attraction_type,
    innercity_transport_type,
    restaurant_type,
)
from chinatravel.symbol_verification.hard_constraint import (
    _infer_lang,
    _set_tool_lang,
    evaluate_constraints_py,
)


MEAL_TYPES = {"breakfast", "lunch", "dinner"}
INTERCITY_TYPES = {"airplane", "train"}
TRICKY_TAGS = {
    "exact_name",
    "time_window",
    "sequence",
    "tight_budget",
    "transport_modes",
    "day_specific",
    "multi_type",
}

ROOM_TYPE_LABELS = {
    1: {"en": "single-bed rooms", "zh": "单床房"},
    2: {"en": "twin-bed rooms", "zh": "双床房"},
}

TRANSPORT_LABELS = {
    "metro": {"en": "metro", "zh": "地铁"},
    "taxi": {"en": "taxi", "zh": "出租车"},
    "walk": {"en": "walking", "zh": "步行"},
    "airplane": {"en": "airplane", "zh": "飞机"},
    "train": {"en": "train", "zh": "火车"},
}

BASE_QUERY_TEMPLATES = {
    "en": "{people_phrase} traveling from {start_city} to {target_city} for {days_phrase}.",
    "zh": "我们{people}人从{start_city}出发去{target_city}玩{days}天。",
}

REQUIREMENT_HEADERS = {
    "en": "Requirements:",
    "zh": "要求如下：",
}

TEMPLATE_CATALOG = {
    "trip_days": {
        "category": "basic",
        "en": "The trip must last {days_phrase}.",
        "zh": "行程必须为{days}天。",
    },
    "people_number": {
        "category": "basic",
        "en": "The plan must be for {people_phrase}.",
        "zh": "行程人数必须为{people}人。",
    },
    "tickets_match_people": {
        "category": "basic",
        "en": "Tickets for attractions, intercity transport, and metro rides must match {people_phrase}.",
        "zh": "景点、城际交通和地铁票数必须与{people}位出行人一致。",
    },
    "room_count": {
        "category": "hotel",
        "en": "Each accommodation stay must reserve {rooms_phrase}.",
        "zh": "每晚住宿都必须预订{rooms}间房。",
    },
    "room_type": {
        "category": "hotel",
        "en": "Each accommodation stay must use {room_type_label}.",
        "zh": "每晚住宿都必须选择{room_type_label}。",
    },
    "inner_transport_modes_subset": {
        "category": "transport",
        "en": "Use only {transport_modes} for transportation within the destination city.",
        "zh": "目的地城市内只能使用{transport_modes}出行。",
    },
    "taxi_cars": {
        "category": "transport",
        "en": "Whenever taking a taxi, use {cars_phrase}.",
        "zh": "每次打车都使用{cars}辆出租车。",
    },
    "intercity_modes_include": {
        "category": "transport",
        "en": "The intercity itinerary must include {intercity_modes}.",
        "zh": "城际交通必须包含{intercity_modes}。",
    },
    "required_attraction_names": {
        "category": "attraction",
        "en": "Visit the following attractions: {names}.",
        "zh": "必须安排以下景点：{names}。",
    },
    "required_restaurant_names": {
        "category": "restaurant",
        "en": "Dine at the following restaurants: {names}.",
        "zh": "必须安排以下餐厅：{names}。",
    },
    "required_accommodation_names": {
        "category": "hotel",
        "en": "Stay at the following hotels: {names}.",
        "zh": "必须安排以下酒店：{names}。",
    },
    "required_attraction_types": {
        "category": "attraction",
        "en": "Include the following attraction types: {types}.",
        "zh": "必须包含以下景点类型：{types}。",
    },
    "required_restaurant_types": {
        "category": "restaurant",
        "en": "Include the following restaurant types: {types}.",
        "zh": "必须包含以下餐厅类型：{types}。",
    },
    "required_accommodation_types": {
        "category": "hotel",
        "en": "Include the following hotel feature types: {types}.",
        "zh": "必须包含以下酒店特色类型：{types}。",
    },
    "attraction_on_day": {
        "category": "attraction",
        "en": "Visit {name} on day {day}.",
        "zh": "第{day}天必须安排景点{name}。",
    },
    "restaurant_on_day": {
        "category": "restaurant",
        "en": "Dine at {name} on day {day}.",
        "zh": "第{day}天必须安排餐厅{name}。",
    },
    "accommodation_on_day": {
        "category": "hotel",
        "en": "Stay at {name} on day {day}.",
        "zh": "第{day}天必须安排酒店{name}。",
    },
    "attraction_time_window": {
        "category": "attraction",
        "en": "Schedule {name} between {start_time} and {end_time}.",
        "zh": "必须在{start_time}到{end_time}之间安排{name}。",
    },
    "restaurant_time_window": {
        "category": "restaurant",
        "en": "Schedule {name} between {start_time} and {end_time}.",
        "zh": "必须在{start_time}到{end_time}之间安排{name}。",
    },
    "accommodation_time_window": {
        "category": "hotel",
        "en": "Schedule {name} between {start_time} and {end_time}.",
        "zh": "必须在{start_time}到{end_time}之间安排{name}。",
    },
    "attraction_order": {
        "category": "attraction",
        "en": "Visit {first_name} before {second_name}.",
        "zh": "必须先去{first_name}，再去{second_name}。",
    },
    "total_budget": {
        "category": "budget",
        "en": "Keep the total activity and in-city transportation cost within {limit}.",
        "zh": "活动和市内交通总费用不超过{limit}。",
    },
    "restaurant_budget": {
        "category": "budget",
        "en": "Keep the dining cost within {limit}.",
        "zh": "餐饮费用不超过{limit}。",
    },
    "accommodation_budget": {
        "category": "budget",
        "en": "Keep the accommodation cost within {limit}.",
        "zh": "住宿费用不超过{limit}。",
    },
    "attraction_budget": {
        "category": "budget",
        "en": "Keep the attraction ticket cost within {limit}.",
        "zh": "景点门票费用不超过{limit}。",
    },
    "innercity_budget": {
        "category": "budget",
        "en": "Keep transportation within the destination city within {limit}.",
        "zh": "目的地城市内交通费用不超过{limit}。",
    },
}


@dataclass
class ConstraintCandidate:
    key: str
    code: str
    nl: dict
    category: str
    tags: set = field(default_factory=set)
    hardness: int = 1
    metadata: dict = field(default_factory=dict)

    def text(self, lang):
        return self.nl.get(lang) or self.nl.get("en") or next(iter(self.nl.values()))


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pystr(value):
    return json.dumps(str(value), ensure_ascii=False)


def pyset(values):
    values = list(dict.fromkeys(str(v) for v in values if v))
    if not values:
        return "set()"
    return "{" + ", ".join(pystr(value) for value in values) + "}"


def minute_of(value):
    if not isinstance(value, str) or ":" not in value:
        return None
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def format_minute(value):
    value = max(0, min(23 * 60 + 59, int(value)))
    return f"{value // 60:02d}:{value % 60:02d}"


def activity_position(activity):
    return activity.get("position") or activity.get("end") or activity.get("start") or ""


def iter_day_activities(plan):
    for day_idx, day in enumerate(plan.get("itinerary", []), start=1):
        for activity in day.get("activities", []):
            yield day_idx, activity


def infer_record_lang(plan, requested):
    if requested != "auto":
        return normalize_lang(requested)
    symbolic_input = {
        "start_city": plan.get("start_city", ""),
        "target_city": plan.get("target_city", ""),
    }
    return _infer_lang(symbolic_input)


def text_list(values, lang):
    values = [str(value) for value in values if value]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if lang == "zh":
        return "、".join(values)
    if len(values) == 2:
        return values[0] + " and " + values[1]
    return ", ".join(values[:-1]) + ", and " + values[-1]


def plural_en(count, singular, plural=None):
    if count == 1:
        return f"1 {singular}"
    return f"{count} {plural or singular + 's'}"


def people_phrase_en(people):
    if people == 1:
        return "I am"
    return f"We are {people} people"


def trip_intro(lang, people, start_city, target_city, days):
    if lang == "zh":
        return BASE_QUERY_TEMPLATES[lang].format(
            people=people,
            start_city=start_city,
            target_city=target_city,
            days=days,
        )
    return BASE_QUERY_TEMPLATES[lang].format(
        people_phrase=people_phrase_en(people),
        start_city=start_city,
        target_city=target_city,
        days_phrase=plural_en(days, "day"),
    )


def transport_list(values, lang):
    labels = [TRANSPORT_LABELS.get(value, {}).get(lang, value) for value in values]
    return text_list(labels, lang)


def unique_items_by_position(items):
    unique = []
    seen = set()
    for item in items:
        position = item.get("position")
        if not position or position in seen:
            continue
        unique.append(item)
        seen.add(position)
    return unique


def total_activity_and_innercity_cost(plan):
    total = 0.0
    for _, activity in iter_day_activities(plan):
        total += float(activity.get("cost", 0) or 0)
        for transport in activity.get("transports", []):
            total += float(transport.get("cost", 0) or 0)
    return total


def cost_by_activity_type(plan, types):
    total = 0.0
    for _, activity in iter_day_activities(plan):
        if activity.get("type") in types:
            total += float(activity.get("cost", 0) or 0)
    return total


def innercity_cost(plan):
    total = 0.0
    for _, activity in iter_day_activities(plan):
        for transport in activity.get("transports", []):
            total += float(transport.get("cost", 0) or 0)
    return total


def budget_limit(actual, rng, margin):
    if actual <= 0:
        return 0
    return int(math.ceil(actual * (1.0 + rng.uniform(0.0, margin))))


def build_nature_language(record, constraints, lang):
    base = trip_intro(
        lang,
        people=record["people_number"],
        start_city=record["start_city"],
        target_city=record["target_city"],
        days=record["days"],
    )
    if not constraints:
        return base
    lines = [base, REQUIREMENT_HEADERS[lang]]
    for idx, constraint in enumerate(constraints, start=1):
        if lang == "zh":
            lines.append(f"{idx}. {constraint.text(lang)}")
        else:
            lines.append(f"{idx}. {constraint.text(lang)}")
    return "\n".join(lines)


def validate_constraints(plan, codes, lang):
    _set_tool_lang(lang)
    results = evaluate_constraints_py(codes, plan, verbose=False)
    return all(results), results


def make_basic_constraints(plan, lang):
    people = int(plan["people_number"])
    days = len(plan.get("itinerary", []))
    constraints = [
        ConstraintCandidate(
            key="trip_days",
            code=f"result=(day_count(plan)=={days})",
            nl={
                "en": f"The trip must last {plural_en(days, 'day')}.",
                "zh": f"行程必须为{days}天。",
            },
            category="basic",
        ),
        ConstraintCandidate(
            key="people_number",
            code=f"result=(people_count(plan)=={people})",
            nl={
                "en": f"The plan must be for {plural_en(people, 'traveler')}.",
                "zh": f"行程人数必须为{people}人。",
            },
            category="basic",
        ),
    ]

    constraints.append(
        ConstraintCandidate(
            key="tickets_match_people",
            code=(
                "result=True\n"
                "for activity in allactivities(plan):\n"
                f"  if activity_type(activity) in ['attraction', 'airplane', 'train'] and activity_tickets(activity)!={people}: result=False\n"
                f"  if innercity_transport_type(activity_transports(activity))=='metro'and metro_tickets(activity_transports(activity))!={people}: result=False"
            ),
            nl={
                "en": f"Tickets for attractions, intercity transport, and metro rides must match {plural_en(people, 'traveler')}.",
                "zh": f"景点、城际交通和地铁票数必须与{people}位出行人一致。",
            },
            category="basic",
            hardness=1,
        )
    )
    return constraints


def make_room_constraints(plan):
    constraints = []
    rooms = set()
    room_types = set()
    for _, activity in iter_day_activities(plan):
        if activity.get("type") == "accommodation":
            if activity.get("rooms"):
                rooms.add(int(activity["rooms"]))
            if activity.get("room_type"):
                room_types.add(int(activity["room_type"]))

    if len(rooms) == 1:
        rooms_value = next(iter(rooms))
        constraints.append(
            ConstraintCandidate(
                key="room_count",
                code=(
                    "result=True\n"
                    "for activity in allactivities(plan):\n"
                    f"  if activity_type(activity)=='accommodation' and room_count(activity)!={rooms_value}: result=False"
                ),
                nl={
                    "en": f"Each accommodation stay must reserve {plural_en(rooms_value, 'room')}.",
                    "zh": f"每晚住宿都必须预订{rooms_value}间房。",
                },
                category="hotel",
                tags={"room"},
                hardness=2,
            )
        )

    if len(room_types) == 1:
        room_type_value = next(iter(room_types))
        label_en = ROOM_TYPE_LABELS.get(room_type_value, {}).get("en", f"room type {room_type_value}")
        label_zh = ROOM_TYPE_LABELS.get(room_type_value, {}).get("zh", f"{room_type_value}号房型")
        constraints.append(
            ConstraintCandidate(
                key="room_type",
                code=(
                    "result=True\n"
                    "for activity in allactivities(plan):\n"
                    f"  if activity_type(activity)=='accommodation' and room_type(activity)!={room_type_value}: result=False"
                ),
                nl={
                    "en": f"Each accommodation stay must use {label_en}.",
                    "zh": f"每晚住宿都必须选择{label_zh}。",
                },
                category="hotel",
                tags={"room"},
                hardness=2,
            )
        )
    return constraints


def make_transport_constraints(plan):
    constraints = []
    inner_modes = set()
    taxi_cars = set()
    intercity_modes = set()
    for _, activity in iter_day_activities(plan):
        activity_type = activity.get("type")
        if activity_type in INTERCITY_TYPES:
            intercity_modes.add(activity_type)
        transports = activity.get("transports", [])
        mode = innercity_transport_type(transports)
        if mode and mode != "empty":
            inner_modes.add(mode)
            if mode == "taxi" and transports and transports[0].get("cars"):
                taxi_cars.add(int(transports[0]["cars"]))

    if inner_modes:
        constraints.append(
            ConstraintCandidate(
                key="inner_transport_modes_subset",
                code=(
                    "inner_city_transportation_set=set()\n"
                    "for activity in allactivities(plan):\n"
                    "  if activity_transports(activity)!=[]: inner_city_transportation_set.add(innercity_transport_type(activity_transports(activity)))\n"
                    f"result=(inner_city_transportation_set<={pyset(sorted(inner_modes))})"
                ),
                nl={
                    "en": f"Use only {transport_list(sorted(inner_modes), 'en')} for transportation within the destination city.",
                    "zh": f"目的地城市内只能使用{transport_list(sorted(inner_modes), 'zh')}出行。",
                },
                category="transport",
                tags={"transport_modes"},
                hardness=4,
            )
        )

    if len(taxi_cars) == 1:
        cars = next(iter(taxi_cars))
        constraints.append(
            ConstraintCandidate(
                key="taxi_cars",
                code=(
                    "result=True\n"
                    "for activity in allactivities(plan):\n"
                    f"  if innercity_transport_type(activity_transports(activity))=='taxi'and taxi_cars(activity_transports(activity))!={cars}: result=False"
                ),
                nl={
                    "en": f"Whenever taking a taxi, use {plural_en(cars, 'taxi')}.",
                    "zh": f"每次打车都使用{cars}辆出租车。",
                },
                category="transport",
                tags={"transport_modes"},
                hardness=3,
            )
        )

    if intercity_modes:
        constraints.append(
            ConstraintCandidate(
                key="intercity_modes_include",
                code=(
                    "intercity_transport_set=set()\n"
                    "for activity in allactivities(plan):\n"
                    "  if activity_type(activity) in ['train', 'airplane']: intercity_transport_set.add(intercity_transport_type(activity))\n"
                    f"result=({pyset(sorted(intercity_modes))}<=intercity_transport_set)"
                ),
                nl={
                    "en": f"The intercity itinerary must include {transport_list(sorted(intercity_modes), 'en')}.",
                    "zh": f"城际交通必须包含{transport_list(sorted(intercity_modes), 'zh')}。",
                },
                category="transport",
                tags={"transport_modes"},
                hardness=3,
            )
        )
    return constraints


def make_name_and_type_constraints(plan, lang, rng):
    _set_tool_lang(lang)
    target_city = plan["target_city"]
    by_type = {"attraction": [], "restaurant": [], "accommodation": []}
    type_values = {"attraction": [], "restaurant": [], "accommodation": []}

    for day_idx, activity in iter_day_activities(plan):
        position = activity_position(activity)
        if not position:
            continue
        activity_type_value = activity.get("type")
        item = {"day": day_idx, "activity": activity, "position": position}
        if activity_type_value == "attraction":
            by_type["attraction"].append(item)
            concept = attraction_type(activity, target_city)
            if concept:
                type_values["attraction"].append(concept)
        elif activity_type_value in MEAL_TYPES:
            by_type["restaurant"].append(item)
            concept = restaurant_type(activity, target_city)
            if concept and concept != "empty":
                type_values["restaurant"].append(concept)
        elif activity_type_value == "accommodation":
            by_type["accommodation"].append(item)
            concept = accommodation_type(activity, target_city)
            if concept:
                type_values["accommodation"].append(concept)

    constraints = []
    name_specs = [
        (
            "attraction",
            "attraction_name_set",
            "activity_type(activity)=='attraction'",
            "attractions",
            "景点",
            "Visit the following attractions",
        ),
        (
            "restaurant",
            "restaurant_name_set",
            "activity_type(activity) in ['breakfast', 'lunch', 'dinner']",
            "restaurants",
            "餐厅",
            "Dine at the following restaurants",
        ),
        (
            "accommodation",
            "accommodation_name_set",
            "activity_type(activity)=='accommodation'",
            "hotels",
            "酒店",
            "Stay at the following hotels",
        ),
    ]
    for kind, var_name, condition, en_label, zh_label, en_prefix in name_specs:
        items = unique_items_by_position(by_type[kind])
        if not items:
            continue
        sample_size = min(len(items), rng.choice([1, 1, 2, 3]))
        names = [item["position"] for item in rng.sample(items, sample_size)]
        constraints.append(
            ConstraintCandidate(
                key=f"required_{kind}_names",
                code=(
                    f"{var_name}=set()\n"
                    "for activity in allactivities(plan):\n"
                    f"  if {condition}: {var_name}.add(activity_position(activity))\n"
                    f"result=({pyset(names)}<={var_name})"
                ),
                nl={
                    "en": f"{en_prefix}: {text_list(names, 'en')}.",
                    "zh": f"必须安排以下{zh_label}：{text_list(names, 'zh')}。",
                },
                category=kind,
                tags={"exact_name"},
                hardness=5 if sample_size >= 2 else 4,
                metadata={"names": names},
            )
        )

    type_specs = [
        (
            "attraction",
            "attraction_type_set",
            "activity_type(activity)=='attraction'",
            "attraction_type(activity, target_city(plan))",
            "attraction types",
            "景点类型",
        ),
        (
            "restaurant",
            "restaurant_type_set",
            "activity_type(activity) in ['breakfast', 'lunch', 'dinner']",
            "restaurant_type(activity, target_city(plan))",
            "restaurant types",
            "餐厅类型",
        ),
        (
            "accommodation",
            "accommodation_type_set",
            "activity_type(activity)=='accommodation'",
            "accommodation_type(activity, target_city(plan))",
            "hotel feature types",
            "酒店特色类型",
        ),
    ]
    for kind, var_name, condition, value_expr, en_label, zh_label in type_specs:
        values = list(dict.fromkeys(type_values[kind]))
        if not values:
            continue
        sample_size = min(len(values), rng.choice([1, 1, 2]))
        selected = rng.sample(values, sample_size)
        constraints.append(
            ConstraintCandidate(
                key=f"required_{kind}_types",
                code=(
                    f"{var_name}=set()\n"
                    "for activity in allactivities(plan):\n"
                    f"  if {condition}: {var_name}.add({value_expr})\n"
                    f"result=({pyset(selected)}<={var_name})"
                ),
                nl={
                    "en": f"Include the following {en_label}: {text_list(selected, 'en')}.",
                    "zh": f"必须包含以下{zh_label}：{text_list(selected, 'zh')}。",
                },
                category=kind,
                tags={"multi_type"} if sample_size >= 2 else {"type"},
                hardness=4 if sample_size >= 2 else 3,
                metadata={"types": selected},
            )
        )

    constraints.extend(make_day_and_time_constraints(by_type, rng))
    constraints.extend(make_sequence_constraints(by_type["attraction"], rng))
    return constraints


def make_day_and_time_constraints(by_type, rng):
    constraints = []
    for kind, items in by_type.items():
        if not items:
            continue
        item = rng.choice(items)
        day_idx = item["day"]
        position = item["position"]
        activity = item["activity"]
        if kind == "attraction":
            condition = "activity_type(activity)=='attraction'"
            var_name = "day_attraction_name_set"
            en_day_text = f"Visit {position} on day {day_idx}."
            zh_kind = "景点"
        elif kind == "restaurant":
            condition = "activity_type(activity) in ['breakfast', 'lunch', 'dinner']"
            var_name = "day_restaurant_name_set"
            en_day_text = f"Dine at {position} on day {day_idx}."
            zh_kind = "餐厅"
        else:
            condition = "activity_type(activity)=='accommodation'"
            var_name = "day_accommodation_name_set"
            en_day_text = f"Stay at {position} on day {day_idx}."
            zh_kind = "酒店"
        constraints.append(
            ConstraintCandidate(
                key=f"{kind}_on_day",
                code=(
                    f"{var_name}=set()\n"
                    f"for activity in dayactivities(plan, {day_idx}):\n"
                    f"  if {condition}: {var_name}.add(activity_position(activity))\n"
                    f"result=({pyset([position])}<={var_name})"
                ),
                nl={
                    "en": en_day_text,
                    "zh": f"第{day_idx}天必须安排{zh_kind}{position}。",
                },
                category=kind,
                tags={"day_specific", "exact_name"},
                hardness=5,
            )
        )

        start = minute_of(activity.get("start_time"))
        end = minute_of(activity.get("end_time"))
        if start is not None and end is not None and end >= start:
            window_start = format_minute(start - rng.choice([10, 15, 20]))
            window_end = format_minute(end + rng.choice([10, 15, 20]))
            constraints.append(
                ConstraintCandidate(
                    key=f"{kind}_time_window",
                    code=(
                        "result=False\n"
                        "for activity in allactivities(plan):\n"
                        f"  if activity_position(activity)=={pystr(position)}:\n"
                        f"    if activity_start_time(activity)>={pystr(window_start)} and activity_end_time(activity)<={pystr(window_end)}: result=True"
                    ),
                    nl={
                        "en": f"Schedule {position} between {window_start} and {window_end}.",
                        "zh": f"必须在{window_start}到{window_end}之间安排{position}。",
                    },
                    category=kind,
                    tags={"time_window", "exact_name"},
                    hardness=5,
                )
            )
    return constraints


def make_sequence_constraints(attractions, rng):
    if len(attractions) < 2:
        return []
    first_idx = rng.randrange(0, len(attractions) - 1)
    second_idx = rng.randrange(first_idx + 1, len(attractions))
    first = attractions[first_idx]["position"]
    second = attractions[second_idx]["position"]
    return [
        ConstraintCandidate(
            key="attraction_order",
            code=(
                "seen_first=False\n"
                "result=False\n"
                "for activity in allactivities(plan):\n"
                f"  if activity_position(activity)=={pystr(first)}: seen_first=True\n"
                f"  if activity_position(activity)=={pystr(second)} and seen_first: result=True"
            ),
            nl={
                "en": f"Visit {first} before {second}.",
                "zh": f"必须先去{first}，再去{second}。",
            },
            category="attraction",
            tags={"sequence", "exact_name"},
            hardness=6,
        )
    ]


def make_budget_constraints(plan, rng, margin):
    budget_specs = [
        (
            "total_budget",
            total_activity_and_innercity_cost(plan),
            "total_cost=0\nfor activity in allactivities(plan):\n  total_cost+=activity_cost(activity)\n  total_cost += innercity_transport_cost(activity_transports(activity))\nresult=(total_cost<={limit})",
            "Keep the total activity and in-city transportation cost within {limit}.",
            "活动和市内交通总费用不超过{limit}。",
            "budget",
        ),
        (
            "restaurant_budget",
            cost_by_activity_type(plan, MEAL_TYPES),
            "restaurant_cost=0\nfor activity in allactivities(plan):\n  if activity_type(activity) in ['breakfast', 'lunch', 'dinner']: restaurant_cost+=activity_cost(activity)\nresult=(restaurant_cost<={limit})",
            "Keep the dining cost within {limit}.",
            "餐饮费用不超过{limit}。",
            "food",
        ),
        (
            "accommodation_budget",
            cost_by_activity_type(plan, {"accommodation"}),
            "accommodation_cost=0\nfor activity in allactivities(plan):\n  if activity_type(activity)=='accommodation': accommodation_cost+=activity_cost(activity)\nresult=(accommodation_cost<={limit})",
            "Keep the accommodation cost within {limit}.",
            "住宿费用不超过{limit}。",
            "hotel",
        ),
        (
            "attraction_budget",
            cost_by_activity_type(plan, {"attraction"}),
            "attraction_cost=0\nfor activity in allactivities(plan):\n  if activity_type(activity)=='attraction': attraction_cost+=activity_cost(activity)\nresult=(attraction_cost<={limit})",
            "Keep the attraction ticket cost within {limit}.",
            "景点门票费用不超过{limit}。",
            "attraction",
        ),
        (
            "innercity_budget",
            innercity_cost(plan),
            "inner_city_transportation_cost=0\nfor activity in allactivities(plan):\n  inner_city_transportation_cost+=innercity_transport_cost(activity_transports(activity))\nresult=(inner_city_transportation_cost<={limit})",
            "Keep transportation within the destination city within {limit}.",
            "目的地城市内交通费用不超过{limit}。",
            "transport",
        ),
    ]
    constraints = []
    for key, actual, code_template, en_template, zh_template, category in budget_specs:
        if actual <= 0:
            continue
        limit = budget_limit(actual, rng, margin)
        constraints.append(
            ConstraintCandidate(
                key=key,
                code=code_template.format(limit=limit),
                nl={
                    "en": en_template.format(limit=limit),
                    "zh": zh_template.format(limit=limit),
                },
                category=category,
                tags={"tight_budget"},
                hardness=5,
                metadata={"actual_cost": actual, "limit": limit},
            )
        )
    return constraints


def candidate_constraints(plan, lang, rng, budget_margin):
    constraints = []
    constraints.extend(make_room_constraints(plan))
    constraints.extend(make_transport_constraints(plan))
    constraints.extend(make_name_and_type_constraints(plan, lang, rng))
    constraints.extend(make_budget_constraints(plan, rng, budget_margin))
    deduped = []
    seen = set()
    for constraint in constraints:
        if constraint.code in seen:
            continue
        seen.add(constraint.code)
        deduped.append(constraint)
    return deduped


def choose_constraints(candidates, rng, count, min_tricky):
    if not candidates:
        return []
    selected = []
    tricky = [c for c in candidates if c.tags & TRICKY_TAGS]
    rng.shuffle(tricky)
    for candidate in tricky[: min(min_tricky, len(tricky))]:
        selected.append(candidate)

    remaining = [c for c in candidates if c not in selected]
    while remaining and len(selected) < count:
        weights = [max(1, c.hardness) for c in remaining]
        chosen = rng.choices(remaining, weights=weights, k=1)[0]
        selected.append(chosen)
        remaining.remove(chosen)
    rng.shuffle(selected)
    return selected


def plan_to_record(plan_path, plan, args, rng, ordinal):
    lang = infer_record_lang(plan, args.lang)
    _set_tool_lang(lang)
    source_uid = Path(plan_path).stem

    base_constraints = make_basic_constraints(plan, lang) if args.include_basic_constraints else []
    candidates = candidate_constraints(plan, lang, rng, args.budget_margin)

    valid_candidates = []
    rejected = []
    for candidate in candidates:
        ok, results = validate_constraints(plan, [candidate.code], lang)
        if ok:
            valid_candidates.append(candidate)
        else:
            rejected.append({"key": candidate.key, "results": results, "code": candidate.code})

    sampled_count = rng.randint(args.min_constraints, args.max_constraints)
    sampled = choose_constraints(
        valid_candidates,
        rng,
        sampled_count,
        args.min_tricky_constraints,
    )
    selected = base_constraints + sampled
    if len(sampled) < args.min_constraints:
        return None, {
            "source_uid": source_uid,
            "reason": "not_enough_valid_candidates",
            "valid_candidates": len(valid_candidates),
            "rejected_candidates": rejected,
        }

    all_ok, all_results = validate_constraints(plan, [c.code for c in selected], lang)
    if not all_ok:
        return None, {
            "source_uid": source_uid,
            "reason": "selected_constraints_failed_validation",
            "results": all_results,
            "constraints": [c.key for c in selected],
        }

    uid = f"{args.uid_prefix}_{source_uid}_{ordinal:05d}"
    record = {
        "uid": uid,
        "tag": args.tag,
        "start_city": plan["start_city"],
        "target_city": plan["target_city"],
        "days": len(plan.get("itinerary", [])),
        "people_number": int(plan["people_number"]),
        "hard_logic_py": [constraint.code for constraint in selected],
        "hard_logic_nl": [constraint.text(lang) for constraint in selected],
        "nature_language": "",
        "source_plan_uid": source_uid,
        "seed_plan_path": str(Path(plan_path)),
        "generation_profile": {
            "lang": lang,
            "sampled_constraints": len(sampled),
            "valid_candidate_constraints": len(valid_candidates),
            "rejected_candidate_constraints": len(rejected),
            "constraint_keys": [constraint.key for constraint in selected],
            "constraint_categories": [constraint.category for constraint in selected],
            "constraint_tags": [sorted(constraint.tags) for constraint in selected],
        },
    }
    record["nature_language"] = build_nature_language(record, selected, lang)
    return record, None


def command_from_plans(args):
    rng = random.Random(args.seed)
    plans = []
    for path in sorted(Path(args.plans_dir).glob(args.plan_glob)):
        try:
            plan = read_json(path)
        except json.JSONDecodeError:
            continue
        if isinstance(plan, dict) and plan.get("itinerary") and plan.get("start_city") and plan.get("target_city"):
            plans.append((path, plan))
    if args.shuffle:
        rng.shuffle(plans)
    if args.max_seed_plans:
        plans = plans[: args.max_seed_plans]

    output_dir = Path(args.output_dir)
    data_dir = output_dir / "data"
    seed_plan_dir = output_dir / "seed_plans"
    generated = []
    skipped = []

    for ordinal, (path, plan) in enumerate(plans, start=1):
        record, error = plan_to_record(path, plan, args, rng, ordinal)
        if error:
            skipped.append(error)
            continue
        write_json(data_dir / f"{record['uid']}.json", record)
        if args.copy_seed_plans:
            write_json(seed_plan_dir / f"{record['uid']}.json", plan)
        generated.append(record)
        if len(generated) >= args.num_records:
            break

    template_inventory = {}
    for record in generated:
        for key, nl in zip(
            record["generation_profile"]["constraint_keys"],
            record["hard_logic_nl"],
        ):
            template_inventory.setdefault(key, set()).add(nl)

    manifest = {
        "num_records_requested": args.num_records,
        "num_records_generated": len(generated),
        "num_seed_plans_loaded": len(plans),
        "num_seed_plans_skipped": len(skipped),
        "lang": args.lang,
        "seed": args.seed,
        "plans_dir": str(Path(args.plans_dir)),
        "data_dir": str(data_dir),
        "copy_seed_plans": args.copy_seed_plans,
        "skipped": skipped[: args.max_manifest_errors],
        "constraint_template_catalog": TEMPLATE_CATALOG,
        "constraint_template_examples": {
            key: sorted(values)[:5] for key, values in sorted(template_inventory.items())
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def command_seed_queries(args):
    rng = random.Random(args.seed)
    lang = normalize_lang(args.lang)
    cities = list(CITY_NAMES[lang])
    output_dir = Path(args.output_dir)
    records = []
    for idx in range(1, args.num_records + 1):
        start_city, target_city = rng.sample(cities, 2)
        days = rng.randint(args.min_days, args.max_days)
        people = rng.randint(args.min_people, args.max_people)
        uid = f"{args.uid_prefix}_{idx:05d}"
        record = {
            "uid": uid,
            "tag": args.tag,
            "start_city": start_city,
            "target_city": target_city,
            "days": days,
            "people_number": people,
            "hard_logic_py": [
                f"result=(day_count(plan)=={days})",
                f"result=(people_count(plan)=={people})",
            ],
            "hard_logic_nl": [
                f"The trip must last {plural_en(days, 'day')}." if lang == "en" else f"行程必须为{days}天。",
                f"The plan must be for {plural_en(people, 'traveler')}." if lang == "en" else f"行程人数必须为{people}人。",
            ],
            "nature_language": trip_intro(
                lang,
                people=people,
                start_city=start_city,
                target_city=target_city,
                days=days,
            ),
        }
        write_json(output_dir / f"{uid}.json", record)
        records.append(record)
    write_json(
        output_dir / "manifest.json",
        {
            "mode": "seed_queries",
            "num_records_generated": len(records),
            "lang": lang,
            "seed": args.seed,
        },
    )
    print(f"Wrote {len(records)} seed queries to {output_dir}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate synthetic ChinaTravel queries from verified seed plans."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser(
        "seed-queries",
        help="Generate unconstrained base queries for running a planner.",
    )
    seed.add_argument("--output-dir", required=True)
    seed.add_argument("--num-records", type=int, default=100)
    seed.add_argument("--lang", choices=["zh", "en"], default="en")
    seed.add_argument("--seed", type=int, default=2026)
    seed.add_argument("--uid-prefix", default="synthetic_seed")
    seed.add_argument("--tag", default="synthetic_seed")
    seed.add_argument("--min-days", type=int, default=2)
    seed.add_argument("--max-days", type=int, default=5)
    seed.add_argument("--min-people", type=int, default=1)
    seed.add_argument("--max-people", type=int, default=5)
    seed.set_defaults(func=command_seed_queries)

    from_plans = subparsers.add_parser(
        "from-plans",
        help="Sample verified constraints from seed plans and write query records.",
    )
    from_plans.add_argument("--plans-dir", required=True)
    from_plans.add_argument("--output-dir", required=True)
    from_plans.add_argument("--num-records", type=int, default=100)
    from_plans.add_argument("--max-seed-plans", type=int, default=0)
    from_plans.add_argument("--plan-glob", default="*.json")
    from_plans.add_argument("--lang", choices=["auto", "zh", "en"], default="auto")
    from_plans.add_argument("--seed", type=int, default=2026)
    from_plans.add_argument("--uid-prefix", default="synthetic_hard")
    from_plans.add_argument("--tag", default="synthetic_hard")
    from_plans.add_argument("--min-constraints", type=int, default=4)
    from_plans.add_argument("--max-constraints", type=int, default=7)
    from_plans.add_argument("--min-tricky-constraints", type=int, default=2)
    from_plans.add_argument("--budget-margin", type=float, default=0.03)
    from_plans.add_argument("--include-basic-constraints", action="store_true", default=True)
    from_plans.add_argument("--no-basic-constraints", dest="include_basic_constraints", action="store_false")
    from_plans.add_argument("--copy-seed-plans", action="store_true")
    from_plans.add_argument("--shuffle", action="store_true", default=True)
    from_plans.add_argument("--no-shuffle", dest="shuffle", action="store_false")
    from_plans.add_argument("--max-manifest-errors", type=int, default=50)
    from_plans.set_defaults(func=command_from_plans)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "max_seed_plans") and args.max_seed_plans == 0:
        args.max_seed_plans = None
    if hasattr(args, "min_constraints") and args.min_constraints > args.max_constraints:
        parser.error("--min-constraints cannot exceed --max-constraints")
    args.func(args)


if __name__ == "__main__":
    main()
