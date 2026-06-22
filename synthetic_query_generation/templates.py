"""Template metadata and shared labels for synthetic query generation."""

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
    "not_constraint",
    "or_group",
    "exact_time",
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
    "attraction_exact_time": {
        "category": "attraction",
        "en": "Schedule {name} exactly from {start_time} to {end_time}.",
        "zh": "必须精确在{start_time}到{end_time}之间安排{name}。",
    },
    "restaurant_exact_time": {
        "category": "restaurant",
        "en": "Schedule {name} exactly from {start_time} to {end_time}.",
        "zh": "必须精确在{start_time}到{end_time}之间安排{name}。",
    },
    "accommodation_exact_time": {
        "category": "hotel",
        "en": "Schedule {name} exactly from {start_time} to {end_time}.",
        "zh": "必须精确在{start_time}到{end_time}之间安排{name}。",
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
    "forbidden_attraction_names": {
        "category": "attraction",
        "en": "Do not visit any of the following attractions: {names}.",
        "zh": "不要安排以下任何景点：{names}。",
    },
    "forbidden_restaurant_names": {
        "category": "restaurant",
        "en": "Do not dine at any of the following restaurants: {names}.",
        "zh": "不要安排以下任何餐厅：{names}。",
    },
    "forbidden_accommodation_names": {
        "category": "hotel",
        "en": "Do not stay at any of the following hotels: {names}.",
        "zh": "不要安排以下任何酒店：{names}。",
    },
    "forbidden_attraction_types": {
        "category": "attraction",
        "en": "Do not include any of the following attraction types: {types}.",
        "zh": "不要包含以下任何景点类型：{types}。",
    },
    "forbidden_restaurant_types": {
        "category": "restaurant",
        "en": "Do not include any of the following restaurant types: {types}.",
        "zh": "不要包含以下任何餐厅类型：{types}。",
    },
    "forbidden_accommodation_types": {
        "category": "hotel",
        "en": "Do not include any of the following hotel feature types: {types}.",
        "zh": "不要包含以下任何酒店特色类型：{types}。",
    },
    "forbidden_inner_transport_modes": {
        "category": "transport",
        "en": "Do not use {transport_modes} for transportation within the destination city.",
        "zh": "目的地城市内不要使用{transport_modes}。",
    },
    "forbidden_depart_transport": {
        "category": "transport",
        "en": "Do not use {transport_mode} for the outbound intercity trip.",
        "zh": "去程城际交通不要使用{transport_mode}。",
    },
    "forbidden_return_transport": {
        "category": "transport",
        "en": "Do not use {transport_mode} for the return intercity trip.",
        "zh": "返程城际交通不要使用{transport_mode}。",
    },
    "either_requirement": {
        "category": "logic",
        "en": "Either {first_requirement} Or {second_requirement}",
        "zh": "满足以下二选一要求：{first_requirement} 或 {second_requirement}",
    },
}

