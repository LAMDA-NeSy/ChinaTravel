"""Validation wrappers for generated hard constraints and seed plans."""

from chinatravel.symbol_verification.commonsense_constraint import (
    Is_activity_grounded,
    Is_attractions_correct,
    Is_hotels_correct,
    Is_intercity_transport_correct,
    Is_restaurants_correct,
    Is_space_correct,
    Is_time_correct,
    Is_transport_correct,
    _set_tool_lang as _set_commonsense_tool_lang,
)
from chinatravel.symbol_verification.hard_constraint import (
    _set_tool_lang as _set_hard_tool_lang,
    evaluate_constraints_py,
)


def set_hard_lang(lang):
    _set_hard_tool_lang(lang)


def validate_constraints(plan, codes, lang):
    _set_hard_tool_lang(lang)
    results = evaluate_constraints_py(codes, plan, verbose=False)
    return all(results), results


def seed_plan_commonsense_errors(plan, lang):
    _set_commonsense_tool_lang(lang)
    symbolic_input = {
        "start_city": plan.get("start_city"),
        "target_city": plan.get("target_city"),
        "days": len(plan.get("itinerary", [])),
        "people_number": int(plan.get("people_number", 0)),
    }
    errors = []
    for func in (
        Is_activity_grounded,
        Is_intercity_transport_correct,
        Is_attractions_correct,
        Is_hotels_correct,
        Is_restaurants_correct,
        Is_transport_correct,
        Is_time_correct,
        Is_space_correct,
    ):
        table, info = func(symbolic_input, plan, verbose=False)
        failed_columns = [
            column for column in table.columns if table.loc[0, column] != 0
        ]
        if failed_columns:
            errors.append(
                {
                    "check": func.__name__,
                    "columns": failed_columns,
                    "info": [str(item) for item in info[:3]],
                }
            )
    return errors
