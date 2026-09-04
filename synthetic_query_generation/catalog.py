"""Constraint-template semantics and release profiles."""


CONSTRAINT_GENERATORS = {
    "trip_days": "basic",
    "people_number": "basic",
    "tickets_match_people": "basic",
    "room_count": "room",
    "room_type": "room",
    "inner_transport_modes_subset": "transport",
    "taxi_cars": "transport",
    "intercity_modes_include": "transport",
    "inner_transport_mode_count": "transport_metrics",
    "walking_distance_budget": "transport_metrics",
    "innercity_travel_time_budget": "transport_metrics",
    "required_attraction_names": "name_type",
    "required_restaurant_names": "name_type",
    "required_accommodation_names": "name_type",
    "required_attraction_types": "name_type",
    "required_restaurant_types": "name_type",
    "required_accommodation_types": "name_type",
    "total_attraction_count": "count",
    "attraction_count_on_day": "count",
    "required_meals_on_day": "count",
    "distinct_accommodation_count": "count",
    "free_attraction_count_minimum": "count",
    "attraction_on_day": "day_time",
    "restaurant_on_day": "day_time",
    "accommodation_on_day": "day_time",
    "attraction_time_window": "day_time",
    "restaurant_time_window": "day_time",
    "accommodation_time_window": "day_time",
    "attraction_exact_time": "day_time",
    "restaurant_exact_time": "day_time",
    "accommodation_exact_time": "day_time",
    "attraction_duration_minimum": "schedule",
    "outbound_departure_deadline": "schedule",
    "return_departure_earliest": "schedule",
    "attraction_order": "sequence",
    "attraction_pair_on_day": "relation",
    "cross_category_order": "relation",
    "total_budget": "budget",
    "restaurant_budget": "budget",
    "accommodation_budget": "budget",
    "attraction_budget": "budget",
    "innercity_budget": "budget",
    "daily_budget": "budget",
    "forbidden_attraction_names": "negative",
    "forbidden_restaurant_names": "negative",
    "forbidden_accommodation_names": "negative",
    "forbidden_attraction_types": "negative",
    "forbidden_restaurant_types": "negative",
    "forbidden_accommodation_types": "negative",
    "forbidden_inner_transport_modes": "negative",
    "forbidden_depart_transport": "negative",
    "forbidden_return_transport": "negative",
    "either_requirement": "logic",
}


CONSTRAINT_SEMANTICS_ZH = {
    "trip_days": "行程 itinerary 的天数必须等于指定值。",
    "people_number": "计划中的出行人数必须等于指定值。",
    "tickets_match_people": "所有景点、飞机和火车票数，以及每次地铁票数，都必须等于出行人数。",
    "room_count": "每个住宿活动预订的房间数都必须等于指定值。",
    "room_type": "每个住宿活动的房型编号都必须等于指定值。",
    "inner_transport_modes_subset": "行程中每个活动的入站市内交通链按主方式分类后，所有分类结果必须是给定允许集合的子集；不要求集合中的每种方式都出现。",
    "taxi_cars": "只要使用出租车，每次使用的车辆数都必须等于指定值。",
    "intercity_modes_include": "实际城际交通方式集合必须包含给定的每一种方式。",
    "inner_transport_mode_count": "按每个活动的完整入站市内交通链的主方式分类，指定分类的行程次数必须恰好等于给定值。",
    "walking_distance_budget": "所有市内交通链中的步行路段距离之和不得超过指定公里数。",
    "innercity_travel_time_budget": "整个行程中所有市内交通路段的持续时间之和不得超过指定分钟数。",
    "required_attraction_names": "景点活动中必须覆盖给定的全部景点名称。",
    "required_restaurant_names": "早餐、午餐或晚餐活动中必须覆盖给定的全部餐厅名称。",
    "required_accommodation_names": "住宿活动中必须覆盖给定的全部酒店名称。",
    "required_attraction_types": "景点活动经沙盒查询得到的类型集合必须包含给定的全部类型。",
    "required_restaurant_types": "餐饮活动经沙盒查询得到的菜系集合必须包含给定的全部类型。",
    "required_accommodation_types": "住宿活动经沙盒查询得到的特色类型集合必须包含给定的全部类型。",
    "total_attraction_count": "整个行程中的景点活动数量必须恰好等于指定值。",
    "attraction_count_on_day": "指定天的景点活动数量必须恰好等于指定值。",
    "required_meals_on_day": "指定天必须包含给定的早餐、午餐或晚餐类型；允许同一天包含其他餐次。",
    "distinct_accommodation_count": "住宿活动中不同酒店名称的数量必须恰好等于指定值。",
    "free_attraction_count_minimum": "费用为零的景点活动数量必须不少于指定值。",
    "attraction_on_day": "指定景点必须作为景点活动出现在指定天。",
    "restaurant_on_day": "指定餐厅必须作为餐饮活动出现在指定天。",
    "accommodation_on_day": "指定酒店必须作为住宿活动出现在指定天。",
    "attraction_time_window": "指定景点活动的完整起止区间必须落在给定时间窗口内。",
    "restaurant_time_window": "指定餐饮活动的完整起止区间必须落在给定时间窗口内。",
    "accommodation_time_window": "指定住宿活动的完整起止区间必须落在给定时间窗口内。",
    "attraction_exact_time": "指定景点活动的开始和结束时间必须与给定值完全相同。",
    "restaurant_exact_time": "指定餐饮活动的开始和结束时间必须与给定值完全相同。",
    "accommodation_exact_time": "指定住宿活动的开始和结束时间必须与给定值完全相同。",
    "attraction_duration_minimum": "所有景点活动持续时间之和必须不少于指定分钟数。",
    "outbound_departure_deadline": "按行程顺序找到的第一段城际交通，其出发时间不得晚于指定时刻。",
    "return_departure_earliest": "按行程顺序找到的最后一段城际交通，其出发时间不得早于指定时刻。",
    "attraction_order": "两个不同景点都必须出现，且第一个景点必须先于第二个景点。",
    "attraction_pair_on_day": "两个指定景点都必须作为景点活动出现在指定天。",
    "cross_category_order": "两个指定且带活动类型的 POI 都必须出现，第一个活动必须先于第二个活动。",
    "total_budget": "全部活动费用与市内交通费用之和不得超过指定上限。",
    "restaurant_budget": "所有早餐、午餐和晚餐活动费用之和不得超过指定上限。",
    "accommodation_budget": "所有住宿活动费用之和不得超过指定上限。",
    "attraction_budget": "所有景点活动费用之和不得超过指定上限。",
    "innercity_budget": "整个行程中所有市内交通段费用之和不得超过指定上限。",
    "daily_budget": "指定天内全部活动费用和市内交通费用之和不得超过指定上限。",
    "forbidden_attraction_names": "景点活动中不得出现给定的任何景点名称。",
    "forbidden_restaurant_names": "餐饮活动中不得出现给定的任何餐厅名称。",
    "forbidden_accommodation_names": "住宿活动中不得出现给定的任何酒店名称。",
    "forbidden_attraction_types": "景点活动经沙盒查询得到的类型不得命中给定集合。",
    "forbidden_restaurant_types": "餐饮活动经沙盒查询得到的菜系不得命中给定集合。",
    "forbidden_accommodation_types": "住宿活动经沙盒查询得到的特色类型不得命中给定集合。",
    "forbidden_inner_transport_modes": "行程中每个活动的入站市内交通链按主方式分类后，分类结果不得命中给定集合。",
    "forbidden_depart_transport": "按行程顺序找到的第一段城际交通不得使用给定方式。",
    "forbidden_return_transport": "按行程顺序找到的最后一段城际交通不得使用给定方式。",
    "either_requirement": "两个完整子约束采用包含式 OR；至少一个子约束为真即可。",
}


NEW_CONSTRAINT_KEYS = frozenset(
    {
        "inner_transport_mode_count",
        "walking_distance_budget",
        "innercity_travel_time_budget",
        "total_attraction_count",
        "attraction_count_on_day",
        "required_meals_on_day",
        "distinct_accommodation_count",
        "free_attraction_count_minimum",
        "attraction_duration_minimum",
        "outbound_departure_deadline",
        "return_departure_earliest",
        "attraction_pair_on_day",
        "cross_category_order",
        "daily_budget",
    }
)

FULL_CONSTRAINT_KEYS = frozenset(CONSTRAINT_GENERATORS)
LEGACY_FULL_CONSTRAINT_KEYS = FULL_CONSTRAINT_KEYS - NEW_CONSTRAINT_KEYS

# Preserve the already released 29-key familiar profile as the catalog grows.
FAMILIAR_CONSTRAINT_KEYS = LEGACY_FULL_CONSTRAINT_KEYS - {
    "attraction_on_day",
    "restaurant_on_day",
    "accommodation_on_day",
    "attraction_exact_time",
    "restaurant_exact_time",
    "accommodation_exact_time",
    "attraction_order",
    "forbidden_depart_transport",
    "forbidden_return_transport",
    "either_requirement",
}


def validate_catalog(template_catalog):
    template_keys = set(template_catalog)
    semantic_keys = set(CONSTRAINT_SEMANTICS_ZH)
    generator_keys = set(CONSTRAINT_GENERATORS)
    if template_keys != semantic_keys or template_keys != generator_keys:
        raise ValueError(
            "Constraint catalogs disagree: templates={}, semantics={}, generators={}".format(
                sorted(template_keys), sorted(semantic_keys), sorted(generator_keys)
            )
        )
