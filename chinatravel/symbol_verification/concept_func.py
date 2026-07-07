from chinatravel.environment.tools.accommodations.apis import Accommodations
from chinatravel.environment.tools.restaurants.apis import Restaurants
from chinatravel.environment.tools.attractions.apis import Attractions
from chinatravel.environment.language import CITY_NAMES, normalize_lang


_current_lang = "zh"
_TOOLS_BY_LANG = {}
_CONCEPT_VALUE_ALIASES = {
    "attraction": {
        "Art Museum": "Art museum",
        "Cultural Attractions": "Cultural Landscape",
        "Historical Site": "historical site",
        "Natural Scenery": "natural scenery",
        "Park": "park",
        "red tourism sites": "Red tourism sites",
        "university campus": "University campus",
    },
    "restaurant": {
        "Bread and Desserts": "Bakery and Desserts",
        "cafe": "coffee shop",
        "Fast food and simple meals": "Fast food and casual dining",
        "hot pot": "Hot pot",
    },
    "accommodation": {
        "Air Purifier": "Air purifier",
        "Bed and Breakfast": "homestay",
        "Bed and breakfast": "homestay",
        "Designer Hotel": "Designer hotel",
        "Family Theme Room": "Family-themed room",
        "Family-themed Room": "Family-themed room",
        "Great View from the Window": "Great view from the window",
        "Scenic Window View": "Great view from the window",
        "Instagrammable swimming pool": "Instagrammable pool",
        "Chess and Card Room": "Mahjong and Card Game Room",
        "Mahjong and Card Room": "Mahjong and Card Game Room",
        "Serviced Apartment": "Hotel Apartment",
        "small but beautiful": "small and beautiful",
        "SPA": "Spa",
        "Stunning night views": "Stunning Night Views",
        "Swimming pool": "Swimming Pool",
        "viral swimming pool": "Instagrammable pool",
    },
}
_CONCEPT_LITERAL_ALIASES = {
    alias: canonical
    for aliases in _CONCEPT_VALUE_ALIASES.values()
    for alias, canonical in aliases.items()
}
_POI_NAME_ALIASES = {
    "Bistro Sola": "Sola Bistro",
}


def _infer_lang_from_city(city):
    if city in CITY_NAMES["en"]:
        return "en"
    return _current_lang


def _tools_for_lang(lang=None):
    lang = normalize_lang(lang or _current_lang)
    if lang not in _TOOLS_BY_LANG:
        _TOOLS_BY_LANG[lang] = {
            "accommodations": Accommodations(lang=lang),
            "restaurants": Restaurants(lang=lang),
            "attractions": Attractions(lang=lang),
        }
    return _TOOLS_BY_LANG[lang]


def set_concept_func_lang(lang=None):
    global _current_lang
    _current_lang = normalize_lang(lang)


def normalize_concept_value(kind, value):
    if not isinstance(value, str):
        return value
    return _CONCEPT_VALUE_ALIASES.get(kind, {}).get(value, value)


def normalize_poi_name(value):
    if not isinstance(value, str):
        return value
    return _POI_NAME_ALIASES.get(value, value)


def normalize_concept_constraint_source(source):
    if not isinstance(source, str):
        return source
    normalized = source
    for alias, canonical in {**_CONCEPT_LITERAL_ALIASES, **_POI_NAME_ALIASES}.items():
        for quote in ("'", '"'):
            normalized = normalized.replace(
                f"{quote}{alias}{quote}", f"{quote}{canonical}{quote}"
            )
    return normalized


def day_count(plan):
    return len(plan["itinerary"])


def people_count(plan):
    return plan["people_number"]

def start_city(plan):
    return plan["start_city"]

def target_city(plan):
    return plan["target_city"]


def allactivities(plan):
    activity_list = []
    for day_activity in plan["itinerary"]:
        for act in day_activity["activities"]:
            activity_list.append(act)
    return activity_list


def allactivities_count(plan):
    count = 0
    for day_activity in plan["itinerary"]:
        count += len(day_activity["activities"])
    return count


def dayactivities(plan, day):
    activity_list = []
    for act in plan["itinerary"][day - 1]["activities"]:
        activity_list.append(act)
    return activity_list


def activity_position(activity):
    if activity.get("type") in {"airplane", "train"}:
        return ""
    return normalize_poi_name(activity.get("position", ""))


def activity_cost(activity):
    return activity.get("cost", 0)


def activity_price(activity):
    return activity.get("price", 0)


def activity_type(activity):
    return activity.get("type", "")


def activity_tickets(activity):
    return activity.get("tickets", 0)


def activity_transports(activity):
    return activity.get("transports", [])


def activity_start_time(activity):
    return activity.get("start_time")


def activity_end_time(activity):
    return activity.get("end_time")


def activity_time(activity):

    start_time = activity.get("start_time")
    end_time = activity.get("end_time")

    if start_time and end_time:
        st_h, st_m = map(int, start_time.split(":"))
        ed_h, ed_m = map(int, end_time.split(":"))
        return (ed_m - st_m) + (ed_h - st_h) * 60
    else:
        return -1


def poi_recommend_time(city, poi):
    select = _tools_for_lang(_infer_lang_from_city(city))["attractions"].select
    attrction_info = select(city, key="name", func=lambda x: x == poi).iloc[0]
    recommend_time = (attrction_info["recommendmintime"]) * 60
    return recommend_time


def poi_distance(city, poi1, poi2, start_time="00:00", transport_type="walk"):
    from chinatravel.environment.tools.transportation.apis import Transportation

    goto = Transportation(lang=_infer_lang_from_city(city)).goto
    return goto(city, poi1, poi2, start_time, transport_type)[0]["distance"]


def innercity_transport_cost(transports, node=None):
    """
    计算市内交通费用
    Args:
        transports: 交通信息列表
        node: 可选的交通类型筛选 ('walk', 'metro', 'taxi' 或 None)
    Returns:
        float: 选定类型的交通费用总和，如果 node 为 None 则返回所有类型的总和
    """
    cost = 0
    for transport in transports:
        if node is None or transport.get("type") == node:
            cost += transport.get("cost", 0)
    return cost


def innercity_transport_price(transports):
    price = 0
    for transport in transports:
        price += transport["price"]
    return price


def innercity_transport_distance(transports, mode=None):
    """
    计算市内交通距离
    Args:
        transports: 交通信息列表
        mode: 可选的交通类型筛选 ('walk', 'metro', 'taxi' 或 None)
    Returns:
        float: 选定类型的交通距离总和，如果 mode 为 None 则返回所有类型的总和
    """
    distance = 0
    for transport in transports:
        if mode is None or transport.get("type") == mode:
            distance += transport.get("distance", 0)
    return distance


def innercity_transport_time(transports, mode=None):

    def calc_time_delta(end_time, start_time):
        hour1, minu1 = int(end_time.split(":")[0]), int(end_time.split(":")[1])
        hour2, minu2 = int(start_time.split(":")[0]), int(start_time.split(":")[1])

        return (hour1 - hour2) * 60 + (minu1 - minu2)

    time_cost = 0
    for transport in transports:
        time_cost += calc_time_delta(transport["end_time"], transport["start_time"])
    return time_cost

def metro_tickets(transports):
    return transports[1]["tickets"]


def taxi_cars(transports):
    if len(transports) > 0 and "cars" in transports[0]:
        return transports[0]["cars"]
    else:
        return "invalid input"


def room_count(activity):
    return activity.get("rooms", 0)


def room_type(activity):
    return activity.get("room_type", 0)


def restaurant_type(activity, target_city):
    restaurants = _tools_for_lang(_infer_lang_from_city(target_city))["restaurants"]
    position = normalize_poi_name(activity["position"])
    select_food_type = restaurants.select(
        target_city, key="name", func=lambda x: x == position
    )["cuisine"]
    if not select_food_type.empty:
        return normalize_concept_value("restaurant", select_food_type.iloc[0])
    return "empty"


def attraction_type(activity, target_city):
    attractions = _tools_for_lang(_infer_lang_from_city(target_city))["attractions"]
    position = normalize_poi_name(activity["position"])
    select_attr_type = attractions.select(
        target_city, key="name", func=lambda x: x == position
    )["type"]
    if not select_attr_type.empty:
        return normalize_concept_value("attraction", select_attr_type.iloc[0])
    return ""


def accommodation_type(activity, target_city):
    accommodations = _tools_for_lang(_infer_lang_from_city(target_city))["accommodations"]
    position = normalize_poi_name(activity["position"])
    select_hotel_type = accommodations.select(
        target_city, key="name", func=lambda x: x == position
    )["featurehoteltype"]
    if not select_hotel_type.empty:
        return normalize_concept_value("accommodation", select_hotel_type.iloc[0])
    return ""


def innercity_transport_type(transports):
    if len(transports) == 3:
        return transports[1]["mode"]
    elif len(transports) == 1:
        return transports[0]["mode"]
    return "empty"


def intercity_transport_type(activity):
    return activity.get("type", "empty")


def innercity_transport_start_time(transports):
    return transports[0]["start_time"]


def innercity_transport_end_time(transports):
    return transports[len(transports) - 1]["end_time"]

def intercity_transport_origin(activity):
    city_list=["上海", "北京", "深圳", "广州", "重庆", "成都", "杭州", "武汉", "南京","苏州", "Shanghai", "Beijing", "Shenzhen", "Guangzhou", "Chongqing", "Chengdu", "Hangzhou", "Wuhan", "Nanjing","Suzhou"]
    if "start" in activity:
        for city in city_list:
            if city in activity["start"]:
                return city
    return ""

def intercity_transport_destination(activity):
    city_list=["上海", "北京", "深圳", "广州", "重庆", "成都", "杭州", "武汉", "南京","苏州", "Shanghai", "Beijing", "Shenzhen", "Guangzhou", "Chongqing", "Chengdu", "Hangzhou", "Wuhan", "Nanjing","Suzhou"]
    if "end" in activity:
        for city in city_list:
            if city in activity["end"]:
                return city
    return ""

func_dict = {
    "day_count": day_count,
    "people_count": people_count,
    "start_city": start_city,
    "target_city": target_city,
    "allactivities": allactivities,
    "allactivities_count": allactivities_count,
    "activity_position": activity_position,
    "activity_cost": activity_cost,
    "activity_type": activity_type,
    "activity_tickets": activity_tickets,
    "activity_transports": activity_transports,
    "activity_price": activity_price,
    "activity_time": activity_time,
    "poi_recommend_time": poi_recommend_time,
    "poi_distance": poi_distance,
    "metro_tickets": metro_tickets,
    "taxi_cars": taxi_cars,
    "room_count": room_count,
    "room_type": room_type,
    "restaurant_type": restaurant_type,
    "attraction_type": attraction_type,
    "accommodation_type": accommodation_type,
    "innercity_transport_type": innercity_transport_type,
    "innercity_transport_cost": innercity_transport_cost,
    "innercity_transport_price": innercity_transport_price,
    "innercity_transport_start_time": innercity_transport_start_time,
    "innercity_transport_end_time": innercity_transport_end_time,
    "innercity_transport_distance": innercity_transport_distance,
    "intercity_transport_type": intercity_transport_type,
    "dayactivities": dayactivities,
    "activity_start_time": activity_start_time,
    "activity_end_time": activity_end_time,
    "intercity_transport_origin": intercity_transport_origin,
    "intercity_transport_destination": intercity_transport_destination,
    "innercity_transport_time": innercity_transport_time,
}
