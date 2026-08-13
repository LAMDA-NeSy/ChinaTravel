"""Shared helpers for query generation modules."""

import json
import math
from pathlib import Path

from chinatravel.environment.language import normalize_lang

from synthetic_query_generation.templates import (
    BASE_QUERY_TEMPLATES,
    REQUIREMENT_HEADERS,
    TRANSPORT_LABELS,
)


_DB_TOOLS_BY_LANG = {}


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def get_db_tools(lang):
    from chinatravel.environment.tools.accommodations.apis import Accommodations
    from chinatravel.environment.tools.attractions.apis import Attractions
    from chinatravel.environment.tools.restaurants.apis import Restaurants

    lang = normalize_lang(lang)
    if lang not in _DB_TOOLS_BY_LANG:
        _DB_TOOLS_BY_LANG[lang] = {
            "attraction": Attractions(lang=lang),
            "restaurant": Restaurants(lang=lang),
            "accommodation": Accommodations(lang=lang),
        }
    return _DB_TOOLS_BY_LANG[lang]


def clean_values(values):
    cleaned = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        text = str(value).strip()
        if text:
            cleaned.append(text)
    return cleaned


def values_not_used(values, used):
    used = {str(value) for value in used if value}
    return [value for value in clean_values(values) if value not in used]


def sample_from_front(values, rng, sample_size, front_size=30):
    values = list(dict.fromkeys(values))
    if not values:
        return []
    pool = values[: max(sample_size, min(front_size, len(values)))]
    return rng.sample(pool, min(sample_size, len(pool)))


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
    value = max(0, min(24 * 60, int(value)))
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
    from chinatravel.symbol_verification.hard_constraint import _infer_lang

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
        lines.append(f"{idx}. {constraint.text(lang)}")
    return "\n".join(lines)
