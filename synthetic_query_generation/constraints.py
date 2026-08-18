"""Constraint candidate generators and sampling logic."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from synthetic_query_generation.models import (
    ConstraintCandidate,
    ConstraintContext,
    ConstraintGenerationOptions,
    EntityContext,
)
from synthetic_query_generation.templates import (
    INTERCITY_TYPES,
    MEAL_TYPES,
    ROOM_TYPE_LABELS,
    TRANSPORT_LABELS,
    TRICKY_TAGS,
)
from synthetic_query_generation.utils import (
    activity_position,
    budget_limit,
    clean_values,
    cost_by_activity_type,
    format_minute,
    get_db_tools,
    innercity_cost,
    iter_day_activities,
    minute_of,
    plural_en,
    pyset,
    pystr,
    sample_from_front,
    text_list,
    total_activity_and_innercity_cost,
    transport_list,
    unique_items_by_position,
    values_not_used,
)


@lru_cache(maxsize=1)
def _concept_functions():
    from chinatravel.symbol_verification.concept_func import (
        accommodation_type,
        attraction_type,
        innercity_transport_type,
        restaurant_type,
    )

    return {
        "accommodation_type": accommodation_type,
        "attraction_type": attraction_type,
        "innercity_transport_type": innercity_transport_type,
        "restaurant_type": restaurant_type,
    }


@dataclass(frozen=True)
class ConstraintGenerator:
    name: str
    factory: Callable[[ConstraintContext], list[ConstraintCandidate]]
    enabled: Callable[[ConstraintContext], bool] | None = None

    def should_run(self, context):
        if context.options.enabled_generators is not None:
            if self.name not in context.options.enabled_generators:
                return False
        if self.name in context.options.disabled_generators:
            return False
        return self.enabled(context) if self.enabled else True


class ConstraintGeneratorRegistry:
    """Ordered registry for independent constraint candidate generators."""

    def __init__(self):
        self._generators = []

    def register(self, name, factory=None, enabled=None):
        def decorator(func):
            self._generators.append(
                ConstraintGenerator(name=name, factory=func, enabled=enabled)
            )
            return func

        if factory is None:
            return decorator
        return decorator(factory)

    def generate(self, context):
        constraints = []
        for generator in self._generators:
            if generator.should_run(context):
                constraints.extend(generator.factory(context))
        return constraints

    def names(self):
        return [generator.name for generator in self._generators]


DEFAULT_REGISTRY = ConstraintGeneratorRegistry()


def collect_entity_context(plan, lang):
    from synthetic_query_generation.validation import set_hard_lang

    set_hard_lang(lang)
    concept_functions = _concept_functions()
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
            concept = concept_functions["attraction_type"](activity, target_city)
            if concept:
                type_values["attraction"].append(concept)
        elif activity_type_value in MEAL_TYPES:
            by_type["restaurant"].append(item)
            concept = concept_functions["restaurant_type"](activity, target_city)
            if concept and concept != "empty":
                type_values["restaurant"].append(concept)
        elif activity_type_value == "accommodation":
            by_type["accommodation"].append(item)
            concept = concept_functions["accommodation_type"](activity, target_city)
            if concept:
                type_values["accommodation"].append(concept)
    return EntityContext(by_type=by_type, type_values=type_values)


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


@DEFAULT_REGISTRY.register("room")
def make_room_constraints(context):
    plan = context.plan
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
        label_en = ROOM_TYPE_LABELS.get(room_type_value, {}).get(
            "en", f"room type {room_type_value}"
        )
        label_zh = ROOM_TYPE_LABELS.get(room_type_value, {}).get(
            "zh", f"{room_type_value}号房型"
        )
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


@DEFAULT_REGISTRY.register("transport")
def make_transport_constraints(context):
    plan = context.plan
    innercity_transport_type = _concept_functions()["innercity_transport_type"]
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


@DEFAULT_REGISTRY.register("transport_metrics")
def make_transport_metric_constraints(context):
    plan = context.plan
    rng = context.rng
    margin = context.options.budget_margin
    innercity_transport_type = _concept_functions()["innercity_transport_type"]
    mode_counts = {}
    walking_distance = 0.0
    transport_minutes = 0
    transport_times_valid = True

    for _, activity in iter_day_activities(plan):
        transports = activity.get("transports", [])
        mode = innercity_transport_type(transports)
        if mode and mode != "empty":
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        for transport in transports:
            if transport.get("mode") == "walk":
                walking_distance += float(transport.get("distance", 0) or 0)
            start = minute_of(transport.get("start_time"))
            end = minute_of(transport.get("end_time"))
            if start is None or end is None:
                transport_times_valid = False
            else:
                transport_minutes += end - start

    constraints = []
    for mode in ("metro", "taxi", "walk"):
        count = mode_counts.get(mode, 0)
        if count <= 0:
            continue
        mode_en = TRANSPORT_LABELS[mode]["en"]
        mode_zh = TRANSPORT_LABELS[mode]["zh"]
        constraints.append(
            ConstraintCandidate(
                key="inner_transport_mode_count",
                code=(
                    "transport_journey_count=0\n"
                    "for activity in allactivities(plan):\n"
                    f"  if innercity_transport_type(activity_transports(activity))=={pystr(mode)}: transport_journey_count+=1\n"
                    f"result=(transport_journey_count=={count})"
                ),
                nl={
                    "en": f"The itinerary must contain exactly {plural_en(count, mode_en + ' journey')}.",
                    "zh": f"行程中必须恰好包含{count}次{mode_zh}行程。",
                },
                category="transport",
                tags={"count", "transport_modes"},
                hardness=7,
                metadata={"mode": mode, "count": count},
            )
        )

    if walking_distance > 0:
        walking_limit = math.ceil(
            walking_distance * (1.0 + rng.uniform(0.0, margin)) * 10
        ) / 10
        constraints.append(
            ConstraintCandidate(
                key="walking_distance_budget",
                code=(
                    "total_walking_distance=0\n"
                    "for activity in allactivities(plan):\n"
                    "  total_walking_distance+=innercity_transport_distance(activity_transports(activity), 'walk')\n"
                    f"result=(total_walking_distance<={walking_limit})"
                ),
                nl={
                    "en": f"Keep the total walking distance within {walking_limit:g} kilometers.",
                    "zh": f"总步行距离不得超过{walking_limit:g}公里。",
                },
                category="transport",
                tags={"distance", "tight_budget"},
                hardness=8,
                metadata={
                    "actual_distance": round(walking_distance, 4),
                    "limit": walking_limit,
                },
            )
        )

    if transport_times_valid and transport_minutes > 0:
        time_limit = budget_limit(transport_minutes, rng, margin)
        constraints.append(
            ConstraintCandidate(
                key="innercity_travel_time_budget",
                code=(
                    "innercity_travel_minutes=0\n"
                    "for activity in allactivities(plan):\n"
                    "  innercity_travel_minutes+=innercity_transport_time(activity_transports(activity))\n"
                    f"result=(innercity_travel_minutes<={time_limit})"
                ),
                nl={
                    "en": f"Keep the total time spent on in-city transportation within {plural_en(time_limit, 'minute')}.",
                    "zh": f"市内交通总耗时不得超过{time_limit}分钟。",
                },
                category="transport",
                tags={"duration", "tight_budget"},
                hardness=8,
                metadata={
                    "actual_minutes": transport_minutes,
                    "limit": time_limit,
                },
            )
        )
    return constraints


@DEFAULT_REGISTRY.register("name_type")
def make_name_and_type_constraints(context):
    by_type = context.entities.by_type
    type_values = context.entities.type_values
    rng = context.rng
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
    for kind, var_name, condition, _en_label, zh_label, en_prefix in name_specs:
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
    return constraints


@DEFAULT_REGISTRY.register("count")
def make_count_constraints(context):
    plan = context.plan
    rng = context.rng
    constraints = []
    attraction_count = 0
    free_attraction_count = 0
    accommodation_names = set()
    day_attraction_counts = []
    day_meal_types = []
    meal_order = ("breakfast", "lunch", "dinner")
    meal_labels_zh = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
    }

    for day_idx, day in enumerate(plan.get("itinerary", []), start=1):
        attractions_on_day = 0
        meals_on_day = set()
        for activity in day.get("activities", []):
            activity_type_value = activity.get("type")
            if activity_type_value == "attraction":
                attraction_count += 1
                attractions_on_day += 1
                if float(activity.get("cost", 0) or 0) == 0:
                    free_attraction_count += 1
            elif activity_type_value in MEAL_TYPES:
                meals_on_day.add(activity_type_value)
            elif activity_type_value == "accommodation":
                position = activity.get("position", "")
                if position:
                    accommodation_names.add(position)
        if attractions_on_day:
            day_attraction_counts.append((day_idx, attractions_on_day))
        ordered_meals = [meal for meal in meal_order if meal in meals_on_day]
        if len(ordered_meals) >= 2:
            day_meal_types.append((day_idx, ordered_meals))

    if attraction_count:
        constraints.append(
            ConstraintCandidate(
                key="total_attraction_count",
                code=(
                    "attraction_count=0\n"
                    "for activity in allactivities(plan):\n"
                    "  if activity_type(activity)=='attraction': attraction_count+=1\n"
                    f"result=(attraction_count=={attraction_count})"
                ),
                nl={
                    "en": f"Visit exactly {plural_en(attraction_count, 'attraction')} during the trip.",
                    "zh": f"整个行程必须恰好安排{attraction_count}个景点。",
                },
                category="attraction",
                tags={"count"},
                hardness=7,
                metadata={"count": attraction_count},
            )
        )

    rng.shuffle(day_attraction_counts)
    for day_idx, count in day_attraction_counts[:3]:
        constraints.append(
            ConstraintCandidate(
                key="attraction_count_on_day",
                code=(
                    "day_attraction_count=0\n"
                    f"for activity in dayactivities(plan, {day_idx}):\n"
                    "  if activity_type(activity)=='attraction': day_attraction_count+=1\n"
                    f"result=(day_attraction_count=={count})"
                ),
                nl={
                    "en": f"Visit exactly {plural_en(count, 'attraction')} on day {day_idx}.",
                    "zh": f"第{day_idx}天必须恰好安排{count}个景点。",
                },
                category="attraction",
                tags={"count", "day_specific"},
                hardness=8,
                metadata={"day": day_idx, "count": count},
            )
        )

    rng.shuffle(day_meal_types)
    for day_idx, meal_types in day_meal_types[:2]:
        meal_labels_en = [meal.replace("_", " ") for meal in meal_types]
        constraints.append(
            ConstraintCandidate(
                key="required_meals_on_day",
                code=(
                    "day_meal_type_set=set()\n"
                    f"for activity in dayactivities(plan, {day_idx}):\n"
                    "  if activity_type(activity) in ['breakfast', 'lunch', 'dinner']: day_meal_type_set.add(activity_type(activity))\n"
                    f"result=({pyset(meal_types)}<=day_meal_type_set)"
                ),
                nl={
                    "en": f"Day {day_idx} must include {text_list(meal_labels_en, 'en')}.",
                    "zh": f"第{day_idx}天必须包含{text_list([meal_labels_zh[meal] for meal in meal_types], 'zh')}。",
                },
                category="restaurant",
                tags={"day_specific", "meal_types"},
                hardness=7,
                metadata={"day": day_idx, "meal_types": meal_types},
            )
        )

    if accommodation_names:
        distinct_count = len(accommodation_names)
        constraints.append(
            ConstraintCandidate(
                key="distinct_accommodation_count",
                code=(
                    "distinct_accommodation_names=set()\n"
                    "for activity in allactivities(plan):\n"
                    "  if activity_type(activity)=='accommodation': distinct_accommodation_names.add(activity_position(activity))\n"
                    "distinct_accommodation_count=0\n"
                    "for accommodation_name in distinct_accommodation_names:\n"
                    "  distinct_accommodation_count+=1\n"
                    f"result=(distinct_accommodation_count=={distinct_count})"
                ),
                nl={
                    "en": f"Stay at exactly {plural_en(distinct_count, 'different hotel')}.",
                    "zh": f"整个行程必须恰好入住{distinct_count}家不同的酒店。",
                },
                category="hotel",
                tags={"count"},
                hardness=7,
                metadata={"count": distinct_count},
            )
        )

    if free_attraction_count:
        minimum = max(1, free_attraction_count - rng.choice([0, 1, 2]))
        constraints.append(
            ConstraintCandidate(
                key="free_attraction_count_minimum",
                code=(
                    "free_attraction_count=0\n"
                    "for activity in allactivities(plan):\n"
                    "  if activity_type(activity)=='attraction' and activity_cost(activity)==0: free_attraction_count+=1\n"
                    f"result=(free_attraction_count>={minimum})"
                ),
                nl={
                    "en": f"Include at least {plural_en(minimum, 'free attraction')}.",
                    "zh": f"至少安排{minimum}个免费景点。",
                },
                category="attraction",
                tags={"count", "budget"},
                hardness=7,
                metadata={
                    "actual_count": free_attraction_count,
                    "minimum": minimum,
                },
            )
        )
    return constraints


@DEFAULT_REGISTRY.register("day_time")
def make_day_and_time_constraints(context):
    by_type = context.entities.by_type
    rng = context.rng
    constraints = []
    for kind, items in by_type.items():
        if not items:
            continue
        sample_count = min(len(items), rng.choice([1, 2, 2, 3]))
        for item in rng.sample(items, sample_count):
            day_idx = item["day"]
            position = item["position"]
            activity = item["activity"]
            if kind == "attraction":
                condition = "activity_type(activity)=='attraction'"
                var_name = "day_attraction_name_set"
                en_day_text = f"Visit {position} on day {day_idx}."
                en_time_prefix = "Visit"
                zh_kind = "景点"
            elif kind == "restaurant":
                condition = "activity_type(activity) in ['breakfast', 'lunch', 'dinner']"
                var_name = "day_restaurant_name_set"
                en_day_text = f"Dine at {position} on day {day_idx}."
                en_time_prefix = "Dine at"
                zh_kind = "餐厅"
            else:
                condition = "activity_type(activity)=='accommodation'"
                var_name = "day_accommodation_name_set"
                en_day_text = f"Stay at {position} on day {day_idx}."
                en_time_prefix = "Stay at"
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
                window_start = format_minute(start - rng.choice([5, 10, 15]))
                window_end = format_minute(end + rng.choice([5, 10, 15]))
                constraints.append(
                    ConstraintCandidate(
                        key=f"{kind}_time_window",
                        code=(
                            "result=False\n"
                            "for activity in allactivities(plan):\n"
                            f"  if {condition} and activity_position(activity)=={pystr(position)}:\n"
                            f"    if activity_start_time(activity)>={pystr(window_start)} and activity_end_time(activity)<={pystr(window_end)}: result=True"
                        ),
                        nl={
                            "en": f"{en_time_prefix} {position} between {window_start} and {window_end}.",
                            "zh": f"必须在{window_start}到{window_end}之间安排{position}。",
                        },
                        category=kind,
                        tags={"time_window", "exact_name"},
                        hardness=6,
                    )
                )
                exact_start = activity.get("start_time")
                exact_end = activity.get("end_time")
                constraints.append(
                    ConstraintCandidate(
                        key=f"{kind}_exact_time",
                        code=(
                            "result=False\n"
                            "for activity in allactivities(plan):\n"
                            f"  if {condition} and activity_position(activity)=={pystr(position)}:\n"
                            f"    if activity_start_time(activity)=={pystr(exact_start)} and activity_end_time(activity)=={pystr(exact_end)}: result=True"
                        ),
                        nl={
                            "en": f"{en_time_prefix} {position} exactly from {exact_start} to {exact_end}.",
                            "zh": f"必须精确在{exact_start}到{exact_end}之间安排{position}。",
                        },
                        category=kind,
                        tags={"exact_time", "time_window", "exact_name"},
                        hardness=9,
                    )
                )
    return constraints


@DEFAULT_REGISTRY.register("schedule")
def make_schedule_constraints(context):
    plan = context.plan
    rng = context.rng
    attraction_minutes = 0
    intercity_activities = []

    for _, activity in iter_day_activities(plan):
        activity_type_value = activity.get("type")
        if activity_type_value == "attraction":
            start = minute_of(activity.get("start_time"))
            end = minute_of(activity.get("end_time"))
            attraction_minutes += -1 if start is None or end is None else end - start
        elif activity_type_value in INTERCITY_TYPES:
            intercity_activities.append(activity)

    constraints = []
    if attraction_minutes > 0:
        minimum = int(attraction_minutes * rng.uniform(0.78, 0.92))
        minimum = max(30, (minimum // 15) * 15)
        minimum = min(minimum, attraction_minutes)
        constraints.append(
            ConstraintCandidate(
                key="attraction_duration_minimum",
                code=(
                    "attraction_minutes=0\n"
                    "for activity in allactivities(plan):\n"
                    "  if activity_type(activity)=='attraction': attraction_minutes+=activity_time(activity)\n"
                    f"result=(attraction_minutes>={minimum})"
                ),
                nl={
                    "en": f"Spend at least {plural_en(minimum, 'minute')} visiting attractions.",
                    "zh": f"景点游览总时长至少为{minimum}分钟。",
                },
                category="attraction",
                tags={"duration"},
                hardness=7,
                metadata={
                    "actual_minutes": attraction_minutes,
                    "minimum": minimum,
                },
            )
        )

    if intercity_activities:
        outbound = intercity_activities[0]
        outbound_start = minute_of(outbound.get("start_time"))
        if outbound_start is not None:
            deadline = format_minute(outbound_start + rng.choice([15, 30, 45]))
            constraints.append(
                ConstraintCandidate(
                    key="outbound_departure_deadline",
                    code=(
                        "result=False\n"
                        "outbound_intercity_found=False\n"
                        "for activity in allactivities(plan):\n"
                        "  if activity_type(activity) in ['train', 'airplane'] and not outbound_intercity_found:\n"
                        f"    result=(activity_start_time(activity)<={pystr(deadline)})\n"
                        "    outbound_intercity_found=True"
                    ),
                    nl={
                        "en": f"The outbound intercity trip must depart no later than {deadline}.",
                        "zh": f"去程城际交通必须在{deadline}之前（含该时刻）出发。",
                    },
                    category="transport",
                    tags={"directional_time", "time_window"},
                    hardness=8,
                    metadata={
                        "actual_start_time": outbound.get("start_time"),
                        "deadline": deadline,
                    },
                )
            )

    if len(intercity_activities) >= 2:
        returning = intercity_activities[-1]
        return_start = minute_of(returning.get("start_time"))
        if return_start is not None:
            earliest = format_minute(return_start - rng.choice([15, 30, 45]))
            constraints.append(
                ConstraintCandidate(
                    key="return_departure_earliest",
                    code=(
                        "result=False\n"
                        "for activity in allactivities(plan):\n"
                        "  if activity_type(activity) in ['train', 'airplane']:\n"
                        f"    result=(activity_start_time(activity)>={pystr(earliest)})"
                    ),
                    nl={
                        "en": f"The return intercity trip must depart no earlier than {earliest}.",
                        "zh": f"返程城际交通不得早于{earliest}出发。",
                    },
                    category="transport",
                    tags={"directional_time", "time_window"},
                    hardness=8,
                    metadata={
                        "actual_start_time": returning.get("start_time"),
                        "earliest": earliest,
                    },
                )
            )
    return constraints


@DEFAULT_REGISTRY.register("sequence")
def make_sequence_constraints(context):
    attractions = unique_items_by_position(context.entities.by_type["attraction"])
    rng = context.rng
    if len(attractions) < 2:
        return []
    constraints = []
    seen = set()
    max_pairs = min(4, len(attractions) - 1)
    attempts = 0
    while len(constraints) < max_pairs and attempts < max_pairs * 10:
        attempts += 1
        first_idx = rng.randrange(0, len(attractions) - 1)
        second_idx = rng.randrange(first_idx + 1, len(attractions))
        first = attractions[first_idx]["position"]
        second = attractions[second_idx]["position"]
        if (first, second) in seen:
            continue
        seen.add((first, second))
        constraints.append(
            ConstraintCandidate(
                key="attraction_order",
                code=(
                    "seen_first=False\n"
                    "result=False\n"
                    "for activity in allactivities(plan):\n"
                    f"  if activity_type(activity)=='attraction' and activity_position(activity)=={pystr(first)}: seen_first=True\n"
                    f"  if activity_type(activity)=='attraction' and activity_position(activity)=={pystr(second)} and seen_first: result=True"
                ),
                nl={
                    "en": f"Visit {first} before {second}.",
                    "zh": f"必须先去{first}，再去{second}。",
                },
                category="attraction",
                tags={"sequence", "exact_name"},
                hardness=7,
            )
        )
    return constraints


@DEFAULT_REGISTRY.register("relation")
def make_relation_constraints(context):
    plan = context.plan
    rng = context.rng
    constraints = []
    attractions_by_day = {}

    for item in context.entities.by_type["attraction"]:
        attractions_by_day.setdefault(item["day"], []).append(item)
    eligible_days = [
        (day_idx, unique_items_by_position(items))
        for day_idx, items in attractions_by_day.items()
        if len(unique_items_by_position(items)) >= 2
    ]
    rng.shuffle(eligible_days)
    for day_idx, items in eligible_days[:3]:
        first, second = rng.sample(items, 2)
        names = [first["position"], second["position"]]
        constraints.append(
            ConstraintCandidate(
                key="attraction_pair_on_day",
                code=(
                    "day_attraction_name_set=set()\n"
                    f"for activity in dayactivities(plan, {day_idx}):\n"
                    "  if activity_type(activity)=='attraction': day_attraction_name_set.add(activity_position(activity))\n"
                    f"result=({pyset(names)}<=day_attraction_name_set)"
                ),
                nl={
                    "en": f"Visit both {text_list(names, 'en')} on day {day_idx}.",
                    "zh": f"第{day_idx}天同时游览{text_list(names, 'zh')}。",
                },
                category="attraction",
                tags={"day_specific", "exact_name", "relation"},
                hardness=8,
                metadata={"day": day_idx, "names": names},
            )
        )

    kind_by_type = {
        "attraction": "attraction",
        "breakfast": "restaurant",
        "lunch": "restaurant",
        "dinner": "restaurant",
        "accommodation": "accommodation",
    }
    ordered_items = []
    for _, activity in iter_day_activities(plan):
        kind = kind_by_type.get(activity.get("type"))
        position = activity.get("position", "")
        if kind and position:
            ordered_items.append({"kind": kind, "position": position})

    pair_candidates = []
    for first_index, first in enumerate(ordered_items):
        for second in ordered_items[first_index + 1 :]:
            if first["kind"] == second["kind"]:
                continue
            if first["position"] == second["position"]:
                continue
            pair_candidates.append((first, second))
    rng.shuffle(pair_candidates)

    conditions = {
        "attraction": "activity_type(activity)=='attraction'",
        "restaurant": "activity_type(activity) in ['breakfast', 'lunch', 'dinner']",
        "accommodation": "activity_type(activity)=='accommodation'",
    }
    first_phrases_en = {
        "attraction": "Visit {name}",
        "restaurant": "Dine at {name}",
        "accommodation": "Stay at {name}",
    }
    second_phrases_en = {
        "attraction": "visiting {name}",
        "restaurant": "dining at {name}",
        "accommodation": "staying at {name}",
    }
    phrases_zh = {
        "attraction": "游览{name}",
        "restaurant": "在{name}用餐",
        "accommodation": "入住{name}",
    }
    seen_pairs = set()
    for first, second in pair_candidates:
        pair_key = (
            first["kind"],
            first["position"],
            second["kind"],
            second["position"],
        )
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        constraints.append(
            ConstraintCandidate(
                key="cross_category_order",
                code=(
                    "first_activity_seen=False\n"
                    "result=False\n"
                    "for activity in allactivities(plan):\n"
                    f"  if {conditions[first['kind']]} and activity_position(activity)=={pystr(first['position'])}: first_activity_seen=True\n"
                    f"  if {conditions[second['kind']]} and activity_position(activity)=={pystr(second['position'])} and first_activity_seen: result=True"
                ),
                nl={
                    "en": (
                        first_phrases_en[first["kind"]].format(
                            name=first["position"]
                        )
                        + " before "
                        + second_phrases_en[second["kind"]].format(
                            name=second["position"]
                        )
                        + "."
                    ),
                    "zh": (
                        "先"
                        + phrases_zh[first["kind"]].format(name=first["position"])
                        + "，再"
                        + phrases_zh[second["kind"]].format(
                            name=second["position"]
                        )
                        + "。"
                    ),
                },
                category="logic",
                tags={"sequence", "cross_category", "exact_name"},
                hardness=9,
                metadata={"first": first, "second": second},
            )
        )
        if len(seen_pairs) >= 4:
            break
    return constraints


def negative_constraints_enabled(context):
    return context.options.include_negative_constraints


@DEFAULT_REGISTRY.register("negative", enabled=negative_constraints_enabled)
def make_negative_constraints(context):
    plan = context.plan
    lang = context.lang
    rng = context.rng
    innercity_transport_type = _concept_functions()["innercity_transport_type"]
    by_type = context.entities.by_type
    type_values = context.entities.type_values
    target_city = plan["target_city"]
    tools = get_db_tools(lang)
    constraints = []

    used_names = {
        kind: {item["position"] for item in items if item.get("position")}
        for kind, items in by_type.items()
    }
    used_types = {
        kind: set(clean_values(values))
        for kind, values in type_values.items()
    }

    name_specs = [
        (
            "attraction",
            tools["attraction"].data[target_city],
            "name",
            "attraction_name_set",
            "activity_type(activity)=='attraction'",
            "attractions",
            "景点",
        ),
        (
            "restaurant",
            tools["restaurant"].data[target_city],
            "name",
            "restaurant_name_set",
            "activity_type(activity) in ['breakfast', 'lunch', 'dinner']",
            "restaurants",
            "餐厅",
        ),
        (
            "accommodation",
            tools["accommodation"].data[target_city],
            "name",
            "accommodation_name_set",
            "activity_type(activity)=='accommodation'",
            "hotels",
            "酒店",
        ),
    ]
    for kind, data, column, var_name, condition, en_label, zh_label in name_specs:
        if column not in data:
            continue
        candidates = values_not_used(data[column].tolist(), used_names[kind])
        selected = sample_from_front(
            candidates, rng, rng.choice([1, 2, 2, 3]), front_size=40
        )
        if not selected:
            continue
        constraints.append(
            ConstraintCandidate(
                key=f"forbidden_{kind}_names",
                code=(
                    f"{var_name}=set()\n"
                    "for activity in allactivities(plan):\n"
                    f"  if {condition}: {var_name}.add(activity_position(activity))\n"
                    f"result=not({pyset(selected)}&{var_name})"
                ),
                nl={
                    "en": f"Do not include any of these {en_label}: {text_list(selected, 'en')}.",
                    "zh": f"不要安排以下任何{zh_label}：{text_list(selected, 'zh')}。",
                },
                category=kind,
                tags={"not_constraint", "exact_name"},
                hardness=7 if len(selected) >= 2 else 6,
                metadata={"forbidden_names": selected},
            )
        )

    type_specs = [
        (
            "attraction",
            tools["attraction"].data[target_city],
            "type",
            "attraction_type_set",
            "activity_type(activity)=='attraction'",
            "attraction types",
            "景点类型",
        ),
        (
            "restaurant",
            tools["restaurant"].data[target_city],
            "cuisine",
            "restaurant_type_set",
            "activity_type(activity) in ['breakfast', 'lunch', 'dinner']",
            "restaurant types",
            "餐厅类型",
        ),
        (
            "accommodation",
            tools["accommodation"].data[target_city],
            "featurehoteltype",
            "accommodation_type_set",
            "activity_type(activity)=='accommodation'",
            "hotel feature types",
            "酒店特色类型",
        ),
    ]
    for kind, data, column, var_name, condition, en_label, zh_label in type_specs:
        if column not in data:
            continue
        value_counts = data[column].value_counts()
        candidates = values_not_used(value_counts.index.tolist(), used_types[kind])
        selected = sample_from_front(
            candidates, rng, rng.choice([1, 1, 2]), front_size=12
        )
        if not selected:
            continue
        constraints.append(
            ConstraintCandidate(
                key=f"forbidden_{kind}_types",
                code=(
                    f"{var_name}=set()\n"
                    "for activity in allactivities(plan):\n"
                    f"  if {condition}: {var_name}.add({kind}_type(activity, target_city(plan)))\n"
                    f"result=not({pyset(selected)}&{var_name})"
                ),
                nl={
                    "en": f"Do not include any of these {en_label}: {text_list(selected, 'en')}.",
                    "zh": f"不要包含以下任何{zh_label}：{text_list(selected, 'zh')}。",
                },
                category=kind,
                tags={"not_constraint", "type"},
                hardness=7,
                metadata={"forbidden_types": selected},
            )
        )

    inner_modes = set()
    intercity_positions = []
    for _, activity in iter_day_activities(plan):
        transports = activity.get("transports", [])
        mode = innercity_transport_type(transports)
        if mode and mode != "empty":
            inner_modes.add(mode)
        if activity.get("type") in INTERCITY_TYPES:
            intercity_positions.append(activity.get("type"))

    forbidden_modes = [mode for mode in ["metro", "taxi", "walk"] if mode not in inner_modes]
    selected_modes = sample_from_front(
        forbidden_modes, rng, rng.choice([1, 1, 2]), front_size=3
    )
    if selected_modes:
        constraints.append(
            ConstraintCandidate(
                key="forbidden_inner_transport_modes",
                code=(
                    "inner_city_transportation_set=set()\n"
                    "for activity in allactivities(plan):\n"
                    "  if activity_transports(activity)!=[]: inner_city_transportation_set.add(innercity_transport_type(activity_transports(activity)))\n"
                    f"result=not({pyset(selected_modes)}&inner_city_transportation_set)"
                ),
                nl={
                    "en": f"Do not use {transport_list(selected_modes, 'en')} for transportation within the destination city.",
                    "zh": f"目的地城市内不要使用{transport_list(selected_modes, 'zh')}。",
                },
                category="transport",
                tags={"not_constraint", "transport_modes"},
                hardness=8,
                metadata={"forbidden_modes": selected_modes},
            )
        )

    if intercity_positions:
        depart = intercity_positions[0]
        forbidden_depart = "airplane" if depart == "train" else "train"
        constraints.append(
            ConstraintCandidate(
                key="forbidden_depart_transport",
                code=(
                    "intercity_activities=[]\n"
                    "for activity in allactivities(plan):\n"
                    "  if activity_type(activity) in ['train', 'airplane']: intercity_activities.append(activity)\n"
                    "result=False\n"
                    "is_first_intercity=True\n"
                    "for activity in intercity_activities:\n"
                    "  if is_first_intercity:\n"
                    f"    result=(intercity_transport_type(activity)!={pystr(forbidden_depart)})\n"
                    "    is_first_intercity=False"
                ),
                nl={
                    "en": f"Do not use {TRANSPORT_LABELS[forbidden_depart]['en']} for the outbound intercity trip.",
                    "zh": f"去程城际交通不要使用{TRANSPORT_LABELS[forbidden_depart]['zh']}。",
                },
                category="transport",
                tags={"not_constraint", "transport_modes"},
                hardness=5,
                metadata={"forbidden_depart": forbidden_depart},
            )
        )
        ret = intercity_positions[-1]
        forbidden_return = "airplane" if ret == "train" else "train"
        constraints.append(
            ConstraintCandidate(
                key="forbidden_return_transport",
                code=(
                    "intercity_activities=[]\n"
                    "for activity in allactivities(plan):\n"
                    "  if activity_type(activity) in ['train', 'airplane']: intercity_activities.append(activity)\n"
                    "result=False\n"
                    "for activity in intercity_activities:\n"
                    f"  result=(intercity_transport_type(activity)!={pystr(forbidden_return)})"
                ),
                nl={
                    "en": f"Do not use {TRANSPORT_LABELS[forbidden_return]['en']} for the return intercity trip.",
                    "zh": f"返程城际交通不要使用{TRANSPORT_LABELS[forbidden_return]['zh']}。",
                },
                category="transport",
                tags={"not_constraint", "transport_modes"},
                hardness=5,
                metadata={"forbidden_return": forbidden_return},
            )
        )
    return constraints


@DEFAULT_REGISTRY.register("budget")
def make_budget_constraints(context):
    plan = context.plan
    rng = context.rng
    margin = context.options.budget_margin
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

    daily_costs = []
    for day_idx, day in enumerate(plan.get("itinerary", []), start=1):
        actual = 0.0
        for activity in day.get("activities", []):
            actual += float(activity.get("cost", 0) or 0)
            for transport in activity.get("transports", []):
                actual += float(transport.get("cost", 0) or 0)
        if actual > 0:
            daily_costs.append((day_idx, actual))
    rng.shuffle(daily_costs)
    for day_idx, actual in daily_costs[:3]:
        limit = budget_limit(actual, rng, margin)
        constraints.append(
            ConstraintCandidate(
                key="daily_budget",
                code=(
                    "daily_cost=0\n"
                    f"for activity in dayactivities(plan, {day_idx}):\n"
                    "  daily_cost+=activity_cost(activity)\n"
                    "  daily_cost+=innercity_transport_cost(activity_transports(activity))\n"
                    f"result=(daily_cost<={limit})"
                ),
                nl={
                    "en": f"Keep all activity and transportation costs on day {day_idx} within {limit}.",
                    "zh": f"第{day_idx}天的活动与交通总费用不得超过{limit}。",
                },
                category="budget",
                tags={"day_specific", "tight_budget"},
                hardness=7,
                metadata={
                    "day": day_idx,
                    "actual_cost": actual,
                    "limit": limit,
                },
            )
        )
    return constraints


def dedupe_constraints(constraints):
    deduped = []
    seen = set()
    for constraint in constraints:
        if constraint.code in seen:
            continue
        seen.add(constraint.code)
        deduped.append(constraint)
    return deduped


def candidate_constraints(
    plan,
    lang,
    rng,
    budget_margin=0.03,
    include_negative=True,
    options=None,
    registry=None,
):
    if options is None:
        options = ConstraintGenerationOptions(
            budget_margin=budget_margin,
            include_negative_constraints=include_negative,
        )
    registry = registry or DEFAULT_REGISTRY
    context = ConstraintContext(
        plan=plan,
        lang=lang,
        rng=rng,
        options=options,
        entities_loader=lambda: collect_entity_context(plan, lang),
    )
    return dedupe_constraints(registry.generate(context))


def choose_constraints(
    candidates,
    rng,
    count,
    min_tricky,
    min_logic,
    priority_keys=None,
    min_priority=0,
):
    if not candidates:
        return []
    selected = []
    priority_keys = priority_keys or set()
    priority_candidates = [
        candidate for candidate in candidates if candidate.key in priority_keys
    ]
    rng.shuffle(priority_candidates)
    for candidate in priority_candidates[: min(min_priority, count)]:
        selected.append(candidate)

    logic_candidates = [c for c in candidates if c.tags & {"not_constraint", "or_group"}]
    rng.shuffle(logic_candidates)
    for candidate in logic_candidates:
        if len(selected) >= count:
            break
        current_logic = sum(
            bool(selected_candidate.tags & {"not_constraint", "or_group"})
            for selected_candidate in selected
        )
        if current_logic >= min_logic:
            break
        if candidate not in selected:
            selected.append(candidate)

    tricky = [c for c in candidates if c.tags & TRICKY_TAGS]
    rng.shuffle(tricky)
    for candidate in tricky:
        if len(selected) >= min(min_tricky, count):
            break
        if candidate not in selected:
            selected.append(candidate)

    remaining = [c for c in candidates if c not in selected]
    while remaining and len(selected) < count:
        weights = [max(1, c.hardness) for c in remaining]
        chosen = rng.choices(remaining, weights=weights, k=1)[0]
        selected.append(chosen)
        remaining.remove(chosen)
    rng.shuffle(selected)
    return selected


def make_or_constraints(candidates, rng, max_groups):
    atomic = [
        candidate
        for candidate in candidates
        if "or_group" not in candidate.tags and candidate.category not in {"basic"}
    ]
    if len(atomic) < 2 or max_groups <= 0:
        return []

    pairs = []
    pair_keys = set()
    attempts = 0
    while len(pairs) < max_groups and attempts < max_groups * 20:
        attempts += 1
        first, second = rng.sample(atomic, 2)
        if first.code == second.code:
            continue
        pair_key = tuple(sorted([first.code, second.code]))
        if pair_key in pair_keys:
            continue
        pair_keys.add(pair_key)
        pairs.append((first, second))

    constraints = []
    for first, second in pairs:
        code = (
            "result_list=[]\n"
            f"{first.code}\n"
            "result_list.append(result)\n"
            f"{second.code}\n"
            "result_list.append(result)\n"
            "result=False\n"
            "for r in result_list:\n"
            "  result=result or r"
        )
        constraints.append(
            ConstraintCandidate(
                key="either_requirement",
                code=code,
                nl={
                    "en": f"Either {first.text('en')} Or {second.text('en')}",
                    "zh": f"满足以下二选一要求：{first.text('zh')} 或 {second.text('zh')}",
                },
                category="logic",
                tags={"or_group"} | first.tags | second.tags,
                hardness=max(first.hardness, second.hardness) + 2,
                metadata={
                    "alternatives": [first.key, second.key],
                    "alternative_categories": [first.category, second.category],
                },
            )
        )
    return constraints
