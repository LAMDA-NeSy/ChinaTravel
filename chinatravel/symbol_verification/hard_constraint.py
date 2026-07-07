import sys
import os
import json
import re

from chinatravel.environment.tools.accommodations.apis import Accommodations
from chinatravel.environment.tools.restaurants.apis import Restaurants
from chinatravel.environment.tools.attractions.apis import Attractions
from chinatravel.environment.tools.intercity_transport.apis import IntercityTransport
from chinatravel.environment.tools.transportation.apis import Transportation
from chinatravel.environment.language import CITY_NAMES, normalize_lang

from chinatravel.symbol_verification.concept_func import (
    func_dict,
    normalize_concept_constraint_source,
    normalize_poi_name,
    set_concept_func_lang,
)
from chinatravel.evaluation.utils import load_json_file

import pandas as pd

from copy import deepcopy

accommodation = Accommodations()
restaurants = Restaurants()
attractions = Attractions()
_TOOLS_BY_LANG = {
    "zh": (accommodation, restaurants, attractions)
}


def _infer_lang(symbolic_input):
    city_values = {
        symbolic_input.get("start_city"),
        symbolic_input.get("target_city"),
    }
    if city_values & set(CITY_NAMES["en"]):
        return "en"
    return "zh"


def _set_tool_lang(lang):
    global accommodation, restaurants, attractions
    lang = normalize_lang(lang)
    if lang not in _TOOLS_BY_LANG:
        _TOOLS_BY_LANG[lang] = (
            Accommodations(lang=lang),
            Restaurants(lang=lang),
            Attractions(lang=lang),
        )
    accommodation, restaurants, attractions = _TOOLS_BY_LANG[lang]
    set_concept_func_lang(lang)


_ACTIVITY_POSITION_EQ_RE = re.compile(
    r"^(?P<prefix>\s*if\s+activity_position\(activity\)\s*==\s*)'"
    r"(?P<value>.*)'(?P<suffix>\s*:\s*)$",
    re.MULTILINE,
)
_POI_DISTANCE_TARGET_RE = re.compile(
    r"poi_distance\((?P<prefix>\s*target_city\(plan\)\s*,\s*)'"
    r"(?P<value>[^\n]*)'(?P<suffix>\s*,\s*accommodation_position\s*\))"
)


def _normalize_legacy_hard_logic_py(constraint):
    """Rewrite generated POI string literals that were emitted with single quotes."""
    if not isinstance(constraint, str):
        return constraint

    def replace_activity_position(match):
        return (
            f"{match.group('prefix')}"
            f"{json.dumps(match.group('value'), ensure_ascii=False)}"
            f"{match.group('suffix')}"
        )

    def replace_poi_distance(match):
        return (
            "poi_distance("
            f"{match.group('prefix')}"
            f"{json.dumps(match.group('value'), ensure_ascii=False)}"
            f"{match.group('suffix')}"
        )

    constraint = _ACTIVITY_POSITION_EQ_RE.sub(replace_activity_position, constraint)
    return _POI_DISTANCE_TARGET_RE.sub(replace_poi_distance, constraint)


def calc_cost_from_itinerary_wo_intercity(itinerary, people_number):
    total_cost = 0
    for day in itinerary:
        for activity in day["activities"]:

            for transport in activity.get("transports", []):

                mode = transport["mode"]
                if mode == "taxi":
                    if "cars" in transport.keys():
                        total_cost += transport.get("cars", 0) * transport.get(
                            "cost", 0
                        )
                    else:
                        total_cost += transport.get("tickets", 0) * transport.get(
                            "cost", 0
                        )
                if mode == "metro":
                    total_cost += transport.get("tickets", 0) * transport.get("cost", 0)

            if (
                activity["type"] == "breakfast"
                or activity["type"] == "lunch"
                or activity["type"] == "dinner"
            ):
                total_cost += activity.get("cost", 0) * people_number

            if activity["type"] == "attraction":
                total_cost += activity.get("tickets", 0) * activity.get("cost", 0)
    return total_cost


def get_symbolic_concepts(symbolic_input, plan_json, need_ood=False):

    target_city = symbolic_input["target_city"]
    start_city = symbolic_input["start_city"]

    if need_ood:
        ood_type_dict = {
            "ancient_style": "古风写真",
            "river_he_side": "河边",
            "river_jiang_side": "江边",
            "sea_side": "海边",
            "dating_place": "约会圣地",
        }
        city_dict = {
            "北京": "beijing",
            "上海": "shanghai",
            "南京": "nanjing",
            "苏州": "suzhou",
            "杭州": "hangzhou",
            "深圳": "shenzhen",
            "成都": "chengdu",
            "武汉": "wuhan",
            "广州": "guangzhou",
            "重庆": "chongqing",
        }
        datapath = os.path.dirname(
            os.path.dirname(__file__)
        ) + "/evaluation/eval_annotation/attractions/{}/attractions_tag.csv".format(
            city_dict[target_city]
        )
        ood_attractions_dataframe = pd.read_csv(datapath)
    # Extracting basic information

    try:
        plan_json["itinerary"]
    except:  # raise Exception("The itinerary is empty")
        return None

    days = len(plan_json["itinerary"])
    people_number = plan_json["people_number"]

    # Calculating total cost
    total_cost = 0
    transport_types = set()
    intercity_transport = set()
    train_type = set()

    food_type = set()
    spot_type = set()
    hotel_feature = set()
    hotel_names = set()
    restaurant_names = set()
    attraction_names = set()

    # rooms and room_type are INT
    rooms = 0
    tickets = 0
    room_type = 0

    tickets_list = []
    rooms_list = []
    room_types_list = []

    food_prices = []
    hotel_prices = []
    missing_cost = False

    misssing_type = False

    for day in plan_json["itinerary"]:
        for activity in day["activities"]:
            if not "type" in activity:
                misssing_type = True
                continue

            if "tickets" in activity:
                tickets = activity.get("tickets", 0)
                tickets_list.append(tickets)

            for transport in activity.get("transports", []):
                if "tickets" in transport.keys():
                    tickets = transport.get("tickets", 0)
                    tickets_list.append(tickets)

                mode = transport["mode"]
                if mode == "taxi":
                    if "cars" in transport.keys():
                        total_cost +=  transport.get(
                            "cost", 0
                        )
                    else:
                        total_cost +=  transport.get(
                            "cost", 0
                        )
                if mode == "metro":
                    total_cost += transport.get("cost", 0)

                if mode in ["metro", "taxi"]:
                    transport_types.add(mode)
                if (
                    mode == "walk"
                    and len(activity.get("transports", [])) == 1
                    and transport.get("distance", 2) > 1
                ):
                    transport_types.add(mode)

            if activity["type"] == "airplane":

                if "cost" in activity:
                    total_cost += activity.get("cost", 0)
                else:
                    missing_cost = True
                intercity_transport.add("airplane")

            if activity["type"] == "train":

                if "cost" in activity:
                    total_cost += activity.get("cost", 0)
                else:
                    missing_cost = True
                intercity_transport.add("train")
                train_id = activity.get("TrainID", "")
                if train_id:
                    train_type.add(train_id[0])

            if not "position" in activity:
                continue
            position = normalize_poi_name(activity["position"])

            if (
                activity["type"] == "breakfast"
                or activity["type"] == "lunch"
                or activity["type"] == "dinner"
            ):
                select_food_type = restaurants.select(
                    target_city, key="name", func=lambda x: x == position
                )["cuisine"]
                if not select_food_type.empty:
                    food_type.add(select_food_type.iloc[0])
                restaurant_names.add(position)

                if "cost" in activity:
                    food_prices.append(activity["cost"])
                    total_cost += activity.get("cost", 0) 
                else:
                    missing_cost = True

            if activity["type"] == "accommodation":
                select_hotel_type = accommodation.select(
                    target_city, key="name", func=lambda x: x == position
                )["featurehoteltype"]
                if not select_hotel_type.empty:
                    hotel_feature.add(select_hotel_type.iloc[0])
                hotel_names.add(position)

                if "cost" in activity:
                    hotel_prices.append(activity["cost"])
                    total_cost +=  activity.get("cost", 0)
                else:
                    missing_cost = True

                rooms = activity.get("rooms", 0)
                room_type = activity.get("room_type", 1)

                rooms_list.append(rooms)
                room_types_list.append(room_type)

            if activity["type"] == "attraction":
                select_attraction_type = attractions.select(
                    target_city, key="name", func=lambda x: x == position
                )["type"]
                if not select_attraction_type.empty:
                    spot_type.add(select_attraction_type.iloc[0])

                if need_ood:
                    # print(target_city, symbolic_input)
                    # print(ood_attractions_dataframe)
                    # print(ood_attractions_dataframe.loc[ood_attractions_dataframe['name'] == activity["position"]])

                    attraction_sel = ood_attractions_dataframe.loc[
                        ood_attractions_dataframe["name"] == position
                    ]
                    if len(attraction_sel) > 0:
                        attraction_info = attraction_sel.iloc[0]
                        # print(attraction_info)
                        for ood_type in ood_type_dict:
                            if attraction_info[ood_type] == 1:
                                spot_type.add(ood_type_dict[ood_type])
                attraction_names.add(position)

                if "cost" in activity:
                    total_cost += activity.get("cost", 0)
                else:
                    missing_cost = True
    # print(spot_type)
    # Calculating average food and hotel prices
    food_price = sum(food_prices) / len(food_prices) if food_prices else 0
    hotel_price = sum(hotel_prices) / len(hotel_prices) if hotel_prices else 0

    # change tickets to int
    # new concepts
    """
    cost_attraction
    cost_hotel
    cost_intercity_transport
    intercity_transport_activity['back']['start_time']<=19"
    """
    cost_attraction = 0
    cost_hotel = 0
    cost_intercity_transport = 0
    intercity_transport_activity = {"go": {}, "back": {}}
    cost_intercity_transport_missing = False
    for day in plan_json["itinerary"]:
        for activity in day["activities"]:
            if "type" not in activity:
                continue
            if activity["type"] == "attraction":
                cost_attraction += activity.get("tickets", 0) * activity.get("cost", 0)
            if activity["type"] == "airplane" or activity["type"] == "train":
                if "cost" in activity and "tickets" in activity:
                    cost_intercity_transport += activity.get(
                        "tickets", 0
                    ) * activity.get("cost", 0)
                else:
                    cost_intercity_transport_missing = True

            if activity["type"] == "accommodation":
                cost_hotel += activity.get("rooms", 0) * activity.get("cost", 0)
    from datetime import datetime

    try:
        plan_json["itinerary"][0]
        plan_json["itinerary"][0]["activities"]
        plan_json["itinerary"][0]["activities"][0]
    except:
        return None

    try:
        _go = plan_json["itinerary"][0]["activities"][0]
        _back = plan_json["itinerary"][-1]["activities"][-1]
    except:
        intercity_transport_activity["go"]["start_time"] = None
        intercity_transport_activity["go"]["end_time"] = None
        intercity_transport_activity["back"]["start_time"] = None
        intercity_transport_activity["back"]["end_time"] = None

    try:
        intercity_transport_activity["go"]["start_time"] = datetime.strptime(
            _go["start_time"], "%H:%M"
        ).hour
        intercity_transport_activity["go"]["end_time"] = datetime.strptime(
            _go["end_time"], "%H:%M"
        ).hour
    except:
        intercity_transport_activity["go"]["start_time"] = None
        intercity_transport_activity["go"]["end_time"] = None
    try:
        intercity_transport_activity["back"]["start_time"] = datetime.strptime(
            _back["start_time"], "%H:%M"
        ).hour
        intercity_transport_activity["back"]["end_time"] = datetime.strptime(
            _back["end_time"], "%H:%M"
        ).hour
    except:
        intercity_transport_activity["back"]["start_time"] = None
        intercity_transport_activity["back"]["end_time"] = None

    if len(set(tickets_list)) == 1:
        tickets = tickets_list[0]
    else:
        tickets = None

    if len(set(rooms_list)) == 1:
        rooms = rooms_list[0]
    else:
        rooms = None

    if len(set(room_types_list)) == 1:
        room_type = room_types_list[0]
    else:
        room_type = None

    if missing_cost:
        total_cost = None
    if cost_intercity_transport_missing:
        cost_intercity_transport = None

    if misssing_type:
        total_cost = cost_attraction = cost_hotel = cost_intercity_transport = None

    if need_ood:

        return {
            "days": days,
            "people_number": people_number,
            "cost": total_cost,
            "transport_type": transport_types,
            "intercity_transport": intercity_transport,
            "train_type": train_type,
            "food_type": food_type,
            "spot_type": spot_type,
            "hotel_feature": hotel_feature,
            "food_price": food_price,
            "hotel_price": hotel_price,
            "hotel_names": hotel_names,
            "restaurant_names": restaurant_names,
            "attraction_names": attraction_names,
            "tickets": tickets,
            "rooms": rooms,
            "room_type": room_type,
            "cost_attraction": cost_attraction,
            "cost_hotel": cost_hotel,
            "cost_intercity_transport": cost_intercity_transport,
            "intercity_transport_activity": intercity_transport_activity,
        }
    else:
        return {
            "days": days,
            "people_number": people_number,
            "cost": total_cost,
            "transport_type": transport_types,
            "intercity_transport": intercity_transport,
            "train_type": train_type,
            "food_type": food_type,
            "spot_type": spot_type,
            "hotel_feature": hotel_feature,
            "food_price": food_price,
            "hotel_price": hotel_price,
            "hotel_names": hotel_names,
            "restaurant_names": restaurant_names,
            "attraction_names": attraction_names,
            "tickets": tickets,
            "rooms": rooms,
            "room_type": room_type,
        }


def evaluate_constraints(extracted_vars, hard_logic):
    if extracted_vars is None:
        return [False] * len(hard_logic)

    results = []
    for constraint in hard_logic:
        try:
            # Evaluate the constraint in a safe manner
            result = eval(constraint, {"__builtins__": None}, extracted_vars)
            results.append(result)
        except Exception as e:
            print(f"Error evaluating constraint '{constraint}': {e}")
            results.append(False)
    return results


def evaluate_constraints_py(hard_logic_py, plan, verbose=False):
    results = []
    debug_logic_py = """
result = True
for activity in allactivities(plan):
    if activity_type(activity) in ['attraction', 'airplane', 'train'] and activity_tickets(activity)!=1:
        print('DEBUG SIGN1!!!')
        print(activity_type(activity), activity_tickets(activity))
    if innercity_transport_type(activity_transports(activity))=='metro' and metro_tickets(activity_transports(activity))!=1:
        print('DEBUG SIGN2!!!')
        print(innercity_transport_type(activity_transports(activity)), metro_tickets(activity_transports(activity)))
"""
    # hard_logic_py.append(debug_logic_py)
    for constraint in hard_logic_py:
        original_constraint = constraint
        constraint = normalize_concept_constraint_source(constraint)
        constraint = _normalize_legacy_hard_logic_py(constraint)
        vars_dict = deepcopy(func_dict)
        vars_dict["plan"] = plan
        # exec(constraint, {"__builtins__": {"set": set, "print": print}}, vars_dict)
        # results.append(vars_dict.get("result", False))
        try:
            # Evaluate the constraint in a safe manner
            exec(
                constraint,
                {
                    "__builtins__": {
                        "set": set,
                    }
                },
                vars_dict,
            )
            res_i = vars_dict.get("result", False)
            # print("result: ", res_i)
            # print(type(res_i))
            results.append(bool(res_i))
            # results.append(result)
        except Exception as e:
            if verbose:
                print(f"Error evaluating constraint '{original_constraint}': {e}")
            results.append(False)
        # print(results)
    return results

if __name__ == "__main__":

    symbolic_input_list = []
    plan_json_list = []

    for i in range(1):
        test_plan_path = "./example/plan_{}.json".format(i + 1)
        test_example_path = "./example/query_{}.json".format(i + 1)
        test_example = load_json_file(test_example_path)
        test_plan = load_json_file(test_plan_path)
        symbolic_input_list.append(test_example)
        plan_json_list.append(test_plan)
    macro_accuracy, micro_accuracy, _ = evaluate_hard_constraints(
        symbolic_input_list, plan_json_list
    )
    print("macro: {}%, micro: {}%".format(macro_accuracy, micro_accuracy))
