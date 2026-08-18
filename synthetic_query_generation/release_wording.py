"""Clarify legacy Phase 2 English wording without changing its DSL semantics."""

from __future__ import annotations

import re


INCLUSIVE_OR_PREFIX = (
    "Satisfy at least one of these two requirements (both are allowed):"
)


def _replace(pattern, replacement, text, key):
    updated, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise ValueError(
            "Could not rewrite legacy wording for {}: {!r}".format(key, text)
        )
    return updated


def clarify_constraint_text(key, text, metadata=None):
    """Return wording that explicitly matches the generated constraint program.

    The function is intentionally idempotent so that release exports can be
    rebuilt from either the original competition records or a clarified copy.
    """

    metadata = metadata or {}
    if key == "either_requirement":
        if text.startswith(INCLUSIVE_OR_PREFIX):
            return text
        if not text.startswith("Either ") or text.count(". Or ") != 1:
            raise ValueError("Unrecognized either_requirement wording: {!r}".format(text))
        first, second = text[len("Either ") :].split(". Or ", 1)
        alternative_keys = metadata.get("alternatives", [])
        if len(alternative_keys) != 2:
            raise ValueError("either_requirement metadata does not name two alternatives")
        first = clarify_constraint_text(alternative_keys[0], first + ".")
        second = clarify_constraint_text(alternative_keys[1], second)
        return "{} (A) {} (B) {}".format(INCLUSIVE_OR_PREFIX, first, second)

    if key == "inner_transport_modes_subset":
        if "as the primary modes of in-city journeys" in text:
            return text
        return _replace(
            r"^Use only (.+) for transportation within the destination city\.$",
            r"Use only \1 as the primary modes of in-city journeys throughout the itinerary.",
            text,
            key,
        )

    if key == "inner_transport_mode_count":
        if text.startswith("Use ") and " as the primary mode for exactly " in text:
            return text
        match = re.fullmatch(
            r"The itinerary must contain exactly (\d+) (metro|taxi|walking) journeys?\.",
            text,
        )
        if not match:
            raise ValueError("Unrecognized inner_transport_mode_count wording: {!r}".format(text))
        count, mode = match.groups()
        journey = "journey" if count == "1" else "journeys"
        return "Use {} as the primary mode for exactly {} in-city {}.".format(
            mode, count, journey
        )

    if key == "innercity_travel_time_budget":
        if text.startswith("Keep the total duration of all in-city transport segments"):
            return text
        return _replace(
            r"^Keep the total time spent on in-city transportation within (\d+) minutes?\.$",
            r"Keep the total duration of all in-city transport segments within \1 minutes.",
            text,
            key,
        )

    window_phrases = {
        "attraction_time_window": ("Visit", "Schedule the entire visit to"),
        "restaurant_time_window": ("Dine at", "Schedule the entire meal at"),
        "accommodation_time_window": ("Stay at", "Schedule the entire stay at"),
    }
    if key in window_phrases:
        old_prefix, new_prefix = window_phrases[key]
        if text.startswith(new_prefix + " "):
            return text
        return _replace(
            r"^{} (.+) between (\d{{2}}:\d{{2}}) and (\d{{2}}:\d{{2}})\.$".format(
                re.escape(old_prefix)
            ),
            r"{} \1 within the time window from \2 to \3.".format(new_prefix),
            text,
            key,
        )

    if key == "attraction_duration_minimum":
        if "minutes in total visiting attractions" in text:
            return text
        return _replace(
            r"^Spend at least (\d+) minutes? visiting attractions\.$",
            r"Spend at least \1 minutes in total visiting attractions.",
            text,
            key,
        )

    budget_rewrites = {
        "total_budget": (
            r"^Keep the total activity and in-city transportation cost within ([0-9.]+)\.$",
            r"Keep the combined cost of all itinerary activities and in-city transportation within \1 CNY.",
        ),
        "restaurant_budget": (
            r"^Keep the dining cost within ([0-9.]+)\.$",
            r"Keep the total dining cost within \1 CNY.",
        ),
        "accommodation_budget": (
            r"^Keep the accommodation cost within ([0-9.]+)\.$",
            r"Keep the total accommodation cost within \1 CNY.",
        ),
        "attraction_budget": (
            r"^Keep the attraction ticket cost within ([0-9.]+)\.$",
            r"Keep the total attraction ticket cost within \1 CNY.",
        ),
        "innercity_budget": (
            r"^Keep transportation within the destination city within ([0-9.]+)\.$",
            r"Keep the total cost of in-city transportation throughout the itinerary within \1 CNY.",
        ),
        "daily_budget": (
            r"^Keep all activity and transportation costs on day (\d+) within ([0-9.]+)\.$",
            r"Keep all activity and transportation costs on day \1 within \2 CNY.",
        ),
    }
    if key in budget_rewrites:
        if text.endswith(" CNY."):
            return text
        pattern, replacement = budget_rewrites[key]
        return _replace(pattern, replacement, text, key)

    if key == "forbidden_inner_transport_modes":
        if "as the primary mode of any in-city journey" in text:
            return text
        return _replace(
            r"^Do not use (.+) for transportation within the destination city\.$",
            r"Do not use \1 as the primary mode of any in-city journey throughout the itinerary.",
            text,
            key,
        )

    return text

