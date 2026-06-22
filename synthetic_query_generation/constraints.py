"""Constraint candidate generators and sampling logic."""

from __future__ import annotations

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
                window_start = format_minute(start - rng.choice([5, 10, 15]))
                window_end = format_minute(end + rng.choice([5, 10, 15]))
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
                            f"  if activity_position(activity)=={pystr(position)}:\n"
                            f"    if activity_start_time(activity)=={pystr(exact_start)} and activity_end_time(activity)=={pystr(exact_end)}: result=True"
                        ),
                        nl={
                            "en": f"Schedule {position} exactly from {exact_start} to {exact_end}.",
                            "zh": f"必须精确在{exact_start}到{exact_end}之间安排{position}。",
                        },
                        category=kind,
                        tags={"exact_time", "time_window", "exact_name"},
                        hardness=9,
                    )
                )
    return constraints


@DEFAULT_REGISTRY.register("sequence")
def make_sequence_constraints(context):
    attractions = context.entities.by_type["attraction"]
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
                    f"  if activity_position(activity)=={pystr(first)}: seen_first=True\n"
                    f"  if activity_position(activity)=={pystr(second)} and seen_first: result=True"
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
                code=f"result=(allactivities(plan)[0]['type']!={pystr(forbidden_depart)})",
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
                code=f"result=(allactivities(plan)[-1]['type']!={pystr(forbidden_return)})",
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


def choose_constraints(candidates, rng, count, min_tricky, min_logic):
    if not candidates:
        return []
    selected = []
    logic_candidates = [c for c in candidates if c.tags & {"not_constraint", "or_group"}]
    rng.shuffle(logic_candidates)
    for candidate in logic_candidates[: min(min_logic, len(logic_candidates), count)]:
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
