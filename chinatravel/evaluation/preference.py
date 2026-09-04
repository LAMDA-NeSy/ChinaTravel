# -*- coding: utf-8 -*-
import json

from chinatravel.environment.language import CITY_NAMES, normalize_lang
from chinatravel.symbol_verification.concept_func import set_concept_func_lang


_current_lang = "zh"
_env_by_lang = {}
_attractions_by_lang = {}
_evaluate_preference_py = None


def _pd():
    import pandas as pd

    return pd


def _infer_lang(symbolic_input=None, plan_json=None):
    city_values = set()
    for source in (symbolic_input, plan_json):
        if isinstance(source, dict):
            city_values.add(source.get("start_city"))
            city_values.add(source.get("target_city"))
    if city_values & set(CITY_NAMES["en"]):
        return "en"
    return "zh"


def _set_preference_lang(lang):
    global _current_lang
    _current_lang = normalize_lang(lang)
    set_concept_func_lang(_current_lang)


def _get_env(lang=None):
    lang = normalize_lang(lang or _current_lang)
    if lang not in _env_by_lang:
        from chinatravel.environment.world_env import WorldEnv

        _env_by_lang[lang] = WorldEnv(lang=lang)
    return _env_by_lang[lang]


def _get_attractions(lang=None):
    lang = normalize_lang(lang or _current_lang)
    if lang not in _attractions_by_lang:
        from chinatravel.evaluation.utils import Attractions

        _attractions_by_lang[lang] = Attractions(lang=lang)
    return _attractions_by_lang[lang]


def _get_evaluate_preference_py():
    global _evaluate_preference_py
    if _evaluate_preference_py is None:
        from chinatravel.symbol_verification.preference import evaluate_preference_py

        _evaluate_preference_py = evaluate_preference_py
    return _evaluate_preference_py


def _goto(*args, **kwargs):
    return _get_env().transportation.goto(*args, **kwargs)


def calc_time_delta(st_time, ed_time):
    st_h, st_m = int(st_time.split(":")[0]), int(st_time.split(":")[1])
    ed_h, ed_m = int(ed_time.split(":")[0]), int(ed_time.split(":")[1])
    return (ed_m - st_m) + (ed_h - st_h) * 60


def convenient_transport(plan_json):
    plan = plan_json["itinerary"]
    time_cost = 0
    transport_count = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if "transports" in activity:
                transport_count += 1
                for transport in activity["transports"]:
                    time_cost += calc_time_delta(
                        transport["start_time"], transport["end_time"]
                    )
    average_time_cost = time_cost / transport_count
    return average_time_cost


def convenient_restaurant(plan_json):
    plan = plan_json["itinerary"]
    restaurant_count = 0
    time_cost = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if activity["type"] in ["breakfast", "lunch", "dinner"]:
                restaurant_count += 1
                for transport in activity["transports"]:
                    time_cost += calc_time_delta(
                        transport["start_time"], transport["end_time"]
                    )
    if restaurant_count == 0:
        return -1
    average_time_cost = time_cost / restaurant_count
    return average_time_cost


def near_poi(plan_json, poi_list):
    poi_count = len(poi_list)
    if poi_count == 0:
        return -1
    plan = plan_json["itinerary"]
    if len(plan) == 1:
        return -1
    city = plan_json["target_city"]
    accommodation_name = ""
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if activity["type"] == "accommodation":
                accommodation_name = activity["position"]
                break
    dist_cost = 0
    for poi in poi_list:
        # print("city", city, "accommodation_name", accommodation_name, "poi", poi)
        dist_cost += _goto(
            city, accommodation_name, poi, start_time="00:00", transport_type="walk"
        )[0]["distance"]
    average_dist_cost = dist_cost / poi_count
    return average_dist_cost


def less_walk(plan_json):
    plan = plan_json["itinerary"]
    walk_distance = 0
    activity_count = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if "transports" in activity:
                for transport in activity["transports"]:
                    if transport["mode"] == "walk":
                        walk_distance += transport["distance"]
                activity_count += 1
    # average_walk_distance = walk_distance / activity_count
    return walk_distance


def meal_cost_ratio(plan_json):
    plan = plan_json["itinerary"]
    meal_cost = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if activity["type"] in ["breakfast", "lunch", "dinner"]:
                meal_cost += activity["cost"]
    return meal_cost / total_cost(plan_json)


def accommodation_cost_ratio(plan_json):
    plan = plan_json["itinerary"]
    accommodation_cost = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if activity["type"] == "accommodation":
                accommodation_cost += activity["cost"]
    return accommodation_cost / total_cost(plan_json)


def attraction_cost_ratio(plan_json):
    plan = plan_json["itinerary"]
    attraction_cost = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if activity["type"] == "attraction":
                attraction_cost += activity["cost"]
    return attraction_cost / total_cost(plan_json)


def total_cost(plan_json):
    plan = plan_json["itinerary"]
    _total_cost = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            _total_cost += activity["cost"]
            for transport in activity["transports"]:
                _total_cost += transport["cost"]
    return _total_cost


def attraction_satisfaction(plan_json):
    plan = plan_json["itinerary"]
    city = plan_json["target_city"]
    recommend_time_list = []
    actual_time_list = []

    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if activity["type"] == "attraction":
                attraction_name = activity["position"]
                attrction_info = _get_attractions().select(
                    city, key="name", func=lambda x: x == attraction_name
                ).iloc[0]
                # attrction_info = ood_attractions_dataframe[ood_attractions_dataframe["name"] == attraction_name].iloc[0]
                recommend_time = (attrction_info["recommendmintime"]) * 60
                actual_time = calc_time_delta(
                    activity["start_time"], activity["end_time"]
                )
                recommend_time_list.append(recommend_time)
                actual_time_list.append(actual_time)
    if len(recommend_time_list) == 0:
        return -1
    # marco = sum(recommend_time_list) / sum(actual_time_list)
    micro = sum(
        [
            recommend_time_list[i] / actual_time_list[i]
            for i in range(len(recommend_time_list))
        ]
    ) / len(recommend_time_list)
    return micro


def attraction_count(plan_json):
    plan = plan_json["itinerary"]
    day_num = len(plan)
    attraction_count = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if activity["type"] == "attraction":
                attraction_count += 1
    average_attraction_count = attraction_count / day_num
    return average_attraction_count


def indoor_attraction_ratio(plan_json):
    plan = plan_json["itinerary"]
    attraction_count = 0
    indoor_attraction_count = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if activity["type"] == "attraction":
                attraction_count += 1
                attraction_name = activity["position"]
                city = plan_json["target_city"]
                attraction_info = _get_attractions().select(
                    city, key="name", func=lambda x: x == attraction_name
                ).iloc[0]
                if attraction_info["indoor"] == 1:
                    indoor_attraction_count += 1
    if attraction_count == 0:
        return -1
    return indoor_attraction_count / attraction_count


def popular_attraction_ratio(plan_json):
    plan = plan_json["itinerary"]
    attraction_count = 0
    popular_score_sum = 0
    for plan_of_day in plan:
        for activity in plan_of_day["activities"]:
            if activity["type"] == "attraction":
                attraction_count += 1
                attraction_name = activity["position"]
                city = plan_json["target_city"]
                attraction_info = _get_attractions().select(
                    city, key="name", func=lambda x: x == attraction_name
                ).iloc[0]
                popular_score_sum += attraction_info["popularity"]
    if attraction_count == 0:
        return -1
    return popular_score_sum / attraction_count


func_list = [
    convenient_transport,
    convenient_restaurant,
    near_poi,
    less_walk,
    meal_cost_ratio,
    accommodation_cost_ratio,
    attraction_cost_ratio,
    total_cost,
    attraction_satisfaction,
    attraction_count,
    indoor_attraction_ratio,
    popular_attraction_ratio,
]


def _evaluate_preference(symbolic_input, plan_json, lang=None):
    _set_preference_lang(lang or _infer_lang(symbolic_input, plan_json))

    result = {}
    poi_list_str = ""
    preference_list = symbolic_input["preference_en"]
    for preference in preference_list:
        if "close to" in preference:
            poi_list_str = preference.split("{")[1].split("}")[0]
            break
    poi_list = poi_list_str.replace("，", ",").split(",")
    poi_list = (
        [poi.strip().strip("'").strip('"') for poi in poi_list]
        if poi_list_str != ""
        else []
    )
    for func in func_list:
        if func == near_poi:
            result[func.__name__] = func(plan_json, poi_list)
        else:
            result[func.__name__] = func(plan_json)
    return result


def evaluate_preference(query_index, query_data, result_data, commonsense_pass, lang=None):
    result = []
    for i in range(len(query_index)):
        if query_index[i] not in commonsense_pass:
            result.append(
                {"data_id": query_index[i]} | {func.__name__: -1 for func in func_list}
            )
            continue
        symbolic_input = query_data[query_index[i]]
        plan_json = result_data[query_index[i]]
        # print("symbolic_input", symbolic_input, "plan_json", plan_json)
        result.append(
            {"data_id": query_index[i]}
            | _evaluate_preference(symbolic_input, plan_json, lang=lang)
        )
    result_df = _pd().DataFrame(result)
    return result_df

def evaluate_preference_v2(query_index, query_data, result_data, pass_id, lang=None):
    result = []
    for i in range(len(query_index)):
        if query_index[i] not in pass_id:
            result.append(
                {"data_id": query_index[i], "concept": -1}
            )
            continue
        
        
        symbolic_input = query_data[query_index[i]]
        plan_json = result_data[query_index[i]]
        _set_preference_lang(lang or _infer_lang(symbolic_input, plan_json))
        # print("symbolic_input", symbolic_input, "plan_json", plan_json)

        if isinstance(symbolic_input["preference_py"], list):
            pre_py = symbolic_input["preference_py"][0]
        else:
            pre_py = symbolic_input["preference_py"]
        
        index = pre_py.find("\n")
        
        concept = pre_py[:index]

        op = concept.split(" ")[0]
        op_concept = concept.split(" ")[1]
        code = pre_py[index + 1 :]

        res = _get_evaluate_preference_py()([(op, op_concept, code)], plan_json)[0]

        result.append(
            {"data_id": query_index[i], "concept": res}
        )
    result_df = _pd().DataFrame(result)
    return result_df


def test():
    test_json_txt = """
    {"people_number":1,"start_city":"深圳","target_city":"南京","itinerary":[{"day":1,"activities":[{"start_time":"06:27","end_time":"15:15","start":"深圳北站","end":"南京南站","TrainID":"D376","type":"train","transports":[],"cost":694.1,"tickets":1},{"position":"中山陵景区","type":"attraction","transports":[{"start":"南京南站","end":"南京南站-地铁站","mode":"walk","start_time":"15:15","end_time":"15:18","cost":0,"distance":0.29},{"start":"南京南站-地铁站","end":"钟灵街-地铁站","mode":"metro","start_time":"15:18","end_time":"15:38","cost":4,"distance":10.21,"tickets":1},{"start":"钟灵街-地铁站","end":"中山陵景区","mode":"walk","start_time":"15:38","end_time":"16:07","cost":0,"distance":2.47}],"cost":0,"start_time":"16:07","end_time":"17:00"},{"position":"朱氏梅花糕","type":"dinner","transports":[{"start":"中山陵景区","end":"钟灵街-地铁站","mode":"walk","start_time":"17:00","end_time":"17:29","cost":0,"distance":2.47},{"start":"钟灵街-地铁站","end":"云南路-地铁站","mode":"metro","start_time":"17:29","end_time":"17:47","cost":4,"distance":9.22,"tickets":1},{"start":"云南路-地铁站","end":"朱氏梅花糕","mode":"walk","start_time":"17:47","end_time":"17:52","cost":0,"distance":0.5}],"cost":6,"start_time":"17:52","end_time":"19:22"},{"position":"行政院","type":"attraction","transports":[{"start":"朱氏梅花糕","end":"云南路-地铁站","mode":"walk","start_time":"19:22","end_time":"19:27","cost":0,"distance":0.5},{"start":"云南路-地铁站","end":"九华山-地铁站","mode":"metro","start_time":"19:27","end_time":"19:32","cost":2,"distance":2.96,"tickets":1},{"start":"九华山-地铁站","end":"行政院","mode":"walk","start_time":"19:32","end_time":"19:39","cost":0,"distance":0.62}],"cost":0,"start_time":"19:39","end_time":"21:09"},{"position":"南京玄武饭店","type":"accommodation","room_type":1,"transports":[{"start":"行政院","end":"九华山-地铁站","mode":"walk","start_time":"21:09","end_time":"21:16","cost":0,"distance":0.62},{"start":"九华山-地铁站","end":"玄武门-地铁站","mode":"metro","start_time":"21:16","end_time":"21:20","cost":2,"distance":2.5,"tickets":1},{"start":"玄武门-地铁站","end":"南京玄武饭店","mode":"walk","start_time":"21:20","end_time":"21:21","cost":0,"distance":0.1}],"cost":556.0,"start_time":"21:21","end_time":"24:00","rooms":1}]},{"day":2,"activities":[{"position":"南京玄武饭店","type":"breakfast","transports":[],"cost":0,"start_time":"08:00","end_time":"08:30"},{"position":"雨花门","type":"attraction","transports":[{"start":"南京玄武饭店","end":"玄武门-地铁站","mode":"walk","start_time":"08:30","end_time":"08:31","cost":0,"distance":0.1},{"start":"玄武门-地铁站","end":"武定门-地铁站","mode":"metro","start_time":"08:31","end_time":"08:43","cost":3,"distance":6.32,"tickets":1},{"start":"武定门-地铁站","end":"雨花门","mode":"walk","start_time":"08:43","end_time":"08:48","cost":0,"distance":0.42}],"cost":0,"start_time":"08:48","end_time":"10:18"},{"position":"江心洲大桥","type":"attraction","transports":[{"start":"雨花门","end":"武定门-地铁站","mode":"walk","start_time":"10:18","end_time":"10:23","cost":0,"distance":0.42},{"start":"武定门-地铁站","end":"雨山路-地铁 站","mode":"metro","start_time":"10:23","end_time":"10:57","cost":5,"distance":17.3,"tickets":1},{"start":"雨山路-地铁站","end":"江心洲大桥","mode":"walk","start_time":"10:57","end_time":"11:31","cost":0,"distance":2.86}],"cost":0,"start_time":"11:31","end_time":"13:01"},{"position":"胡小石纪念馆","type":"attraction","transports":[{"start":"江心洲大桥","end":"雨山路-地铁站","mode":"walk","start_time":"13:01","end_time":"13:35","cost":0,"distance":2.86},{"start":"雨山路-地铁站","end":"文德路-地铁站","mode":"metro","start_time":"13:35","end_time":"13:38","cost":2,"distance":1.8,"tickets":1},{"start":"文德路-地铁站","end":"胡小石纪念馆","mode":"walk","start_time":"13:38","end_time":"13:45","cost":0,"distance":0.61}],"cost":0,"start_time":"13:45","end_time":"15:15"},{"start_time":"17:00","end_time":"14:52","start":"南京站","end":"深圳站","TrainID":"K36","type":"train","transports":[{"start":"胡小石纪念馆","end":"文德路-地铁站","mode":"walk","start_time":"15:15","end_time":"15:22","cost":0,"distance":0.61},{"start":"文德路-地铁站","end":"南京站-地铁站","mode":"metro","start_time":"15:22","end_time":"15:54","cost":5,"distance":16.42,"tickets":1},{"start":"南京站-地铁站","end":"南京站","mode":"walk","start_time":"15:54","end_time":"15:56","cost":0,"distance":0.25}],"cost":462.73,"tickets":1}]}]}
    """
    test_symbolic_input = {"preference_en": ["close to {中山陵景区,行政院}"]}
    plan_json = json.loads(test_json_txt)
    result = _evaluate_preference(test_symbolic_input, plan_json)
    print(result)


if __name__ == "__main__":
    test()
