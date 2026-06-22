# -*- coding: utf-8 -*-
import json
from .examples import EXAMPLE, GLM4_EXAMPLE

import os

cur_dir = os.path.dirname(os.path.abspath(__file__))

example_query_path = os.path.join(cur_dir, "query.json")
example_plan_path = os.path.join(cur_dir, "plan.json")

# 返程交通和返程的交通枢纽

with open(example_query_path, "r", encoding="utf-8") as f:
    example_query = str(json.load(f)["nature_language"]).replace(" ", "")
with open(example_plan_path, "r", encoding="utf-8") as f:
    example_plan = str(json.load(f)).replace(" ", "")

output_format_path = os.path.join(cur_dir, "output_schema.json")
with open(output_format_path, "r", encoding="utf-8") as f:
    output_format = str(json.load(f)).replace(" ", "")

QA_STRING = f"""Query:\n {example_query} \nPlan:\n {example_plan} \n"""


func_doc = """

(1) attractions_keys(city: str)
Description: Returns a list of (key, type) pairs of the attractions data.
Parameters:
city: The city name.
(2) attractions_select(city: str, key, func: Callable = lambda x: True):
Description: Returns a DataFrame with data filtered by the specified key with the specified function.
Parameters:
city: The city name.
key: The key column to filter, only one key can be used.
func: The lambda function applied to the key column, must return a boolean value. Only apply to one key. If not specified, return all data.
(3) attractions_id_is_open(city: str, id: int, time: str):
Description: Returns whether the attraction with the specified ID is open at the specified time.
Parameters:
city: The city name.
id: The ID of the attraction.
time: The time to check, in the format 'HH:MM'.
(4) attractions_nearby(city: str, point: str, topk: int, dist: float = 2):
Description: Returns the top K attractions within the specified distance of the location.
Parameters:
city: The city name.
point: The name of the location.
topk: The number of attractions to return.
dist: The maximum distance from the location, default is 2.
(5) attractions_types(city: str):
Description: Returns a list of unique attraction types.
Parameters:
city: The city name.

(6) accommodations_keys(city: str):
Description: Returns a list of (key, type) pairs of the accommodations data.
Parameters:
city: The city name.
(7) accommodations_select(city: str, key, func: Callable = lambda x: True):
Description: Returns a DataFrame with data filtered by the specified key with the specified function.
Parameters:
city: The city name.
key: The key column to filter, only one key can be used.
func: The lambda function applied to the key column, must return a boolean value. Only apply to one key. If not specified, return all data.
(8) accommodations_nearby(city: str, point: str, topk: int, dist: float = 5):
Description: Returns the top K accommodations within the specified distance of the location.
Parameters:
city: The city name.
point: The name of the location.
topk: The number of accommodations to return.
dist: The maximum distance from the location, default is 5.

(9) restaurants_keys(city: str):
Description: Returns a list of (key, type) pairs of the restaurants data.
Parameters:
city: The city name.
(10) restaurants_select(city: str, key, func: Callable = lambda x: True):
Description: Returns a DataFrame with data filtered by the specified key with the specified function.
city: The city name.
key: The key column to filter, only one key can be used.
func: The lambda function applied to the key column, must return a boolean value. Only apply to one key. If not specified, return all data.
(11) restaurants_id_is_open(city: str, id: int, time: str):
Description: Returns whether the restaurant with the specified ID is open at the specified time and day.
Parameters:
city: The city name.
id: The ID of the restaurant.
time: The time to check, in the format 'HH:MM'.
(12) restaurants_nearby(city: str, point: str, topk: int, dist: float = 2):
Description: Returns the top K restaurants within the specified distance of the location.
Parameters:
city: The city name.
point: The name of the location.
topk: The number of restaurants to return.
dist: The maximum distance from the location, default is 2.
(13) restaurants_with_recommended_food(city: str, food: str):
Description: Returns all restaurants with the specified food in their recommended dishes.
Parameters:
city: The city name.
food: The food to search for.
(14) restaurants_cuisine(city: str):
Description: Returns a list of unique restaurant cuisines.
Parameters:
city: The city name.

(15) goto(city: str, start: str, end: str, start_time: str, transport_type: str):
Description: Returns a list of transportation options between two locations.
Parameters:
city: The city name.
start: The start point's name. Must be a location name and match the data exactly.
end: The end point's name. Must be a location name and match the data exactly.
start_time: The departure time in the format 'HH:MM'.
transport_type: The mode of transportation, must in ['walk', 'taxi', 'metro'].

(16) notedown(description: str, content: str):
Description: Writes the specified content to the notebook.
Parameters:
description: The description of the content.
content: The content to write.

(17) plan(query: str):
Description: Generates a plan based on the notebook content and query.
Parameters:
query: The query to generate a plan for. Don't worry about the notebook content, the planner will read it automatically.

(18) intercity_transport_select(start_city: str, end_city: str, intercity_type: str, earliest_leave_time: str = None):
Description: get the intercity transportation information between two cities. You need to call this function at least twice to get the transportation information between two locations for going and returning.
Parameters:
start_city: The start city name.
end_city: The end city name.
intercity_type: The type of intercity transportation, must in ['train', 'airplane'].
earliest_leave_time: The earliest leave time in the format 'HH:MM'.
Return: The transportation information between two cities sorted by leaving time.


(19) next_page():
Description: Get the next page of the latest Result history if it exists. Because of the length limited, all returned DataFrame information is split into 10 rows per page. You can use this function to get the next page of the Result history. Only DataFrame information can be split into multiple pages. The function should not be used too often, otherwise, you will soon run out of steps.
Parameters:
None

"""


ZEROSHOT_REACT_INSTRUCTION_GLM4 = (
    """Collect information for a query plan using interleaving 'Thought', 'Action', and 'Observation' steps. Ensure you gather valid information related to transportation, dining, attractions, and accommodation. All information including time, cost, location and others must be written in notebook, which will then be input into the Planner tool. Note that the nested use of tools is not allowed. 'Thought' can reason about the current situation, and 'Action' can have 19 different types: (You need to put '<STOP>' at the end of the each Thought and Action)

city_list = ["上海", "北京", "深圳", "广州", "重庆", "苏州", "成都", "杭州", "武汉", "南京"]. All the cities name you use must be in this list.

Before select, you need to use xxx_keys(city) to get the keys of the data, and then use xxx_select(city, key, func) to get the data you want. Also, for cuisine, you can use restaurants_cuisine(city) to get the cuisine list and for type of attractions, you can use attractions_types(city) to get the type list and then you can use xxx_select(city, key, func) to get the data you want with specific cuisine or type.
"""
    + func_doc
    + """Your action will be executed in the following format: action, so any additional text like 'Action: ' is not allowed and just one line is allowed for each action.


You must finish your response within 30 steps including plan, otherwise the system will terminate your response. If you note down too often, you will soon run out of steps. But you can note down multiple pieces of information as a string and then write them all at once.

You must select the transportation, dining, attractions, and accommodation information you need to plan your trip and write them in the notebook. The costs, time, locations and both inner and intercity transportation information must be written in the notebook.

So, please be careful with your response and just search and note down the information you need.

If you live in hotel A and want to go to attraction B, you must notedown the transport information between hotel A and attraction B before planning and the you want to have a meal in restaurant C, you must write down the transportation information between attraction B and restaurant C before planning. Absolutely, you also must notedown the information about the hotel A, attraction B, restaurant C, and the innercity transportation between them. Every day need to be planned in detail, including the meals, attractions, accommodations, and transportation. The plan should be detailed and reasonable, if not specified by user's query, every day should be planned with two or three meals, a reasonable number of attractions, maybe 2-4. The accommodation should be a continuous stay if not specified by user's query. The transportation should be reasonable and the cost should be within the budget. Before plan, think about if there is any information missing in the notebook, if so, you need to search and note down the information. If only one day is planned, accommodation is not necessary.

### EXAMPLE ###
Thought[1]: 用户的指令中，提到和朋友一起，所以是两个人一起，餐饮地铁这些费用都需要*2, 景点一般也是，此外如果有打车需要，一般多人与一人的开销相同。用户希望多坐地铁，因此如果地铁可以到达，尽可能让用户坐地铁，如果乘坐地铁前后需要步行的距离太远，可以考虑在预算范围内打车前往这些地铁不便到达的目的地。另外用户喜欢吃江浙菜，我需要了解一些南京的江浙菜餐馆，用于安排用户的餐饮。首先我需要规划用户从北京抵达南京的方案。<STOP>
Action[1]: intercity_transport_select(start_city='北京', end_city='南京', intercity_type='train')<STOP>
Observation[1]: Please note down what is useful using notedown transport_type.
Results[1]:
[MASKED]
Page/Total: 1/8
Thought[2]: 我还需要查看一下机票，也许有一些更便宜的机票<STOP>
Action[2]: intercity_transport_select(start_city='北京', end_city='南京', intercity_type='airplane')<STOP>
......
### END ###
Note that innercity transportation bwteen locations must be notedown!
!!!MUST not forget to put '<STOP>' at the end of each Thought and Action!!!
!!!Make sure you have notedown the useful information in the Observation part, remember to use notedown transport_type to write the information in the notebook!!!
!!!Use Chinese!!!使用中文!!!

Query:
"""
)


ZEROSHOT_REACT_INSTRUCTION = (
    """Collect information for a query plan using interleaving 'Thought', 'Action', and 'Observation' steps. Ensure you gather valid information related to transportation, dining, attractions, and accommodation. All information including time, cost, location and others must be written in notebook, which will then be input into the Planner tool. Note that transportation bwteen locations must be written in notebook before planning. Note that the nested use of tools is not allowed, 'Thought' can reason about the current situation, and 'Action' can have 19 different types:

city_list = ["上海", "北京", "深圳", "广州", "重庆", "苏州", "成都", "杭州", "武汉", "南京"]. All the cities name you use must be in this list.
"""
    + func_doc
    + """Your action will be executed in the following format: action, so any additional text like 'Action: ' is not allowed and just one line is allowed for each action.

You must finish your response within 30 steps including plan, otherwise the system will terminate your response. If you note down too often, you will soon run out of steps. But you can note down multiple pieces of information as a string WITHIN ONE CALL.

Select the transportation, dining, attractions, and accommodation information you need to plan your trip and write them in the notebook. Not EVERYTHING is needed, only what you need to plan the trip. For example, when you get ten or more accommodations, you only need to note down the information of the accommodation you want to stay in, usually one, and note it down in the notebook. You must not note down all the accommodations information. And usually, 2-4 attractions are enough for one day.

What you note down in the notebook should be a plan or plans for days. May be notedown(description = "Day 1(Day 1 morning is also acceptable)", content = "At 8:00, have breakfast at hotel A, then go to attraction B, using metro(together with the cost, time, stations and other information). Attracion B will cost xxx yuan and xxx hours. Then go to restaurant C for lunch, using taxi(together with the cost, time, distance and other information). Restaurant C will cost xxx yuan.(another attraction is possiple too as long as there is enough time and budget). Then... ###More details here###.")

Do not forget to note down the ###transportation information between locations### before planning. Intercity transportation information should be notedown before planning too.
You need to plan for each day in detail. If only one day is planned, accommodation is not needed. If more than one day is planned, accommodation is necessary. Nights in accommodations should be days-1. For example, if you plan for 3 days, you need to note down 2 nights in accommodations. Do not forget to note down the transportation information between locations before planning. Both going and returning transportation information should be notedown.

Call next_page() only when you need to get the next page of the latest Result history. Once you get the suitable information, you must STOP using this function. !!! Pay attention to function names and parameters, and the format of the data. You must use the correct function names and parameters to get the data you need. If you use the wrong function names or parameters, you will not get the correct data.!!!

The intercity transportation back to the start city must be notedown before planning!!!
The innercity to railway station or airport must be notedown before planning!!!

Query:
"""
)

ZEROSHOT_ACT_INSTRUCTION = (
    """Collect information for a query plan using interleaving 'Action', and 'Observation' steps. Ensure you gather valid information related to transportation(including inter and inner city), dining, attractions, and accommodation. All information including time, cost, location and others must be written in notebook, which will then be input into the Planner tool. Note that the nested use of tools is not allowed. 'Action' can have 19 different types:

city_list = ["上海", "北京", "深圳", "广州", "重庆", "苏州", "成都", "杭州", "武汉", "南京"]. All the cities name you use must be in this list.
"""
    + func_doc
    + """Your action will be executed in the following format: action, so any additional text like 'Action: ' is not allowed and just one line is allowed for each action.

You must finish your response within 30 steps including plan.

Select the transportation, dining, attractions, and accommodation information you need to plan your trip and write them in the notebook. Not EVERYTHING is needed, only what you need to plan the trip. For example, when you get ten or more accommodations, you only need to note down the information of the accommodation you want to stay in, usually one, and note it down in the notebook. You must not note down all the accommodations information. And usually, 2-4 attractions are enough for one day.

What you note down in the notebook should be a plan or plans for days. May be notedown(description = "Day 1(Day 1 morning is also acceptable)", content = "At 8:00, have breakfast at hotel A, then go to attraction B, using metro(together with the cost, time, stations and other information). Attracion B will cost xxx yuan and xxx hours. Then go to restaurant C for lunch, using taxi(together with the cost, time, distance and other information). Restaurant C will cost xxx yuan.(another attraction is possiple too as long as there is enough time and budget). Then... ###More details here###.")

Limination of the plan:
1. Breakfast can be in the hotel for free and must be in 6:00-9:00, lunch must be in 11:00-13:00, dinner must be in 17:00-20:00.
2. The attraction or restaurant must be open when you plan to go there.
3. All activities must not be conflict with each other.
4. The activity before must be finished before the next activity starts.
5. Accommodation should be planned for each night, and the accommodation should be continuous stay if not specified by user's query. If only one day is planned, accommodation is not needed.


### EXAMPLE ###
...... //Some thoughts and actions before planning looking up the information
Action[X]: notedown(description='Day 1', content='At 8:00, have breakfast at hotel A, then go to attraction B, using metro(together with the cost, time, stations and other information). Attracion B will cost xxx yuan and xxx hours. Then go to restaurant C for lunch, using taxi(together with the cost, time, distance and other information). Restaurant C will cost xxx yuan.(another attraction is possiple too as long as there is enough time and budget). Then... ###More details here###.')
...... // More actions and observations
// The first day plan must include the transportation from the start city to the target city, and the last activity must be the transportation back to the start city.
Action[n]:plan(query="我和朋友想去南京玩三天，预算4000元，尽量多坐地铁，喜欢吃江浙菜，请给我们一个旅行规划。")
### EXAMPLE END ###

Do not forget to note down the ###transportation information between locations### before planning. Intercity transportation information should be notedown before planning too.

!!!Must not use next_page() too often!!!

Remember to note down all information you need in the notebook before planning.

!!!The intercity transport back to the start city must be notedown before planning!!!

!!!Use next_page() too often is strictly prohibited!!!
!!!next_page() should only be used when you need to get the next page of the latest Result history. Once you get the suitable information, you must STOP using this function.!!!

Query:
"""
)


ONESHOT_REACT_INSTRUCTION = (
    """Collect information for a query plan using interleaving 'Thought', 'Action', and 'Observation' steps. Ensure you gather valid information related to transportation, dining, attractions, and accommodation. All information including time, cost, location and others must be written in notebook, which will then be input into the Planner tool. Note that transportation bwteen locations must be written in notebook before planning. Note that the nested use of tools is not allowed, 'Thought' can reason about the current situation, and 'Action' can have 19 different types:

city_list = ["上海", "北京", "深圳", "广州", "重庆", "苏州", "成都", "杭州", "武汉", "南京"]. All the cities name you use must be in this list.
"""
    + func_doc
    + """Your action will be executed in the following format: action, so any additional text like 'Action: ' is not allowed and just one line is allowed for each action.

You must finish your response within 50 steps including plan, otherwise the system will terminate your response. If you note down too often, you will soon run out of steps. But you can note down multiple pieces of information as a string WITHIN ONE CALL.

Select the transportation, dining, attractions, and accommodation information you need to plan your trip and write them in the notebook. Not EVERYTHING is needed, only what you need to plan the trip. For example, when you get ten or more accommodations, you only need to note down the information of the accommodation you want to stay in, usually one, and note it down in the notebook. You must not note down all the accommodations information. And usually, 2-4 attractions are enough for one day.

What you note down in the notebook should be a plan or plans for days. May be notedown(description = "Day 1(Day 1 morning is also acceptable)", content = "At 8:00, have breakfast at hotel A, then go to attraction B, using metro(together with the cost, time, stations and other information). Attracion B will cost xxx yuan and xxx hours. Then go to restaurant C for lunch, using taxi(together with the cost, time, distance and other information). Restaurant C will cost xxx yuan.(another attraction is possiple too as long as there is enough time and budget). Then... ###More details here###.")

Do not forget to note down the ###transportation information between locations### before planning. Intercity transportation information should be notedown before planning too.
You need to plan for each day in detail. If only one day is planned, accommodation is not needed. If more than one day is planned, accommodation is necessary. Nights in accommodations should be days-1. For example, if you plan for 3 days, you need to note down 2 nights in accommodations. Do not forget to note down the transportation information between locations before planning. Both going and returning transportation information should be notedown.

Call next_page() only when you need to get the next page of the latest Result history. Once you get the suitable information, you must STOP using this function. !!! Pay attention to function names and parameters, and the format of the data. You must use the correct function names and parameters to get the data you need. If you use the wrong function names or parameters, you will not get the correct data.!!!

The intercity transportation back to the start city must be notedown before planning!!!
The innercity to railway station or airport must be notedown before planning!!!
"""
    + EXAMPLE
    + """

Query:
"""
)

ONESHOT_REACT_INSTRUCTION_GLM4 = (
    """Collect information for a query plan using interleaving 'Thought', 'Action', and 'Observation' steps. Ensure you gather valid information related to transportation, dining, attractions, and accommodation. All information including time, cost, location and others must be written in notebook, which will then be input into the Planner tool. Note that transportation bwteen locations must be written in notebook before planning. Note that the nested use of tools is not allowed, 'Thought' can reason about the current situation, and 'Action' can have 19 different types:

city_list = ["上海", "北京", "深圳", "广州", "重庆", "苏州", "成都", "杭州", "武汉", "南京"]. All the cities name you use must be in this list.
"""
    + func_doc
    + """Your action will be executed in the following format: action, so any additional text like 'Action: ' is not allowed and just one line is allowed for each action.

Each Thought and Action must end with '<STOP>'.

You must finish your response within 30 steps including plan, otherwise the system will terminate your response. If you note down too often, you will soon run out of steps. But you can note down multiple pieces of information as a string WITHIN ONE CALL.

Select the transportation, dining, attractions, and accommodation information you need to plan your trip and write them in the notebook. Not EVERYTHING is needed, only what you need to plan the trip. For example, when you get ten or more accommodations, you only need to note down the information of the accommodation you want to stay in, usually one, and note it down in the notebook. You must not note down all the accommodations information. And usually, 2-4 attractions are enough for one day.

What you note down in the notebook should be a plan or plans for days. May be notedown(description = "Day 1(Day 1 morning is also acceptable)", content = "At 8:00, have breakfast at hotel A, then go to attraction B, using metro(together with the cost, time, stations and other information). Attracion B will cost xxx yuan and xxx hours. Then go to restaurant C for lunch, using taxi(together with the cost, time, distance and other information). Restaurant C will cost xxx yuan.(another attraction is possiple too as long as there is enough time and budget). Then... ###More details here###.")

Do not forget to note down the ###transportation information between locations### before planning. Intercity transportation information should be notedown before planning too.
You need to plan for each day in detail. If only one day is planned, accommodation is not needed. If more than one day is planned, accommodation is necessary. Nights in accommodations should be days-1. For example, if you plan for 3 days, you need to note down 2 nights in accommodations. Do not forget to note down the transportation information between locations before planning. Both going and returning transportation information should be notedown.

Call next_page() only when you need to get the next page of the latest Result history. Once you get the suitable information, you must STOP using this function. !!! Pay attention to function names and parameters, and the format of the data. You must use the correct function names and parameters to get the data you need. If you use the wrong function names or parameters, you will not get the correct data.!!!

The intercity transportation back to the start city must be notedown before planning!!!
The innercity to railway station or airport must be notedown before planning!!!
"""
    + GLM4_EXAMPLE
    + """

Query:
"""
)


DIRECT_PROMPT = (
    """You are a proficient planner. Based on the provided information and query, please give me a detailed plan. Note that all the information in your plan should be derived from the provided data. You must adhere to the format given in the schema. Your plan should be in JSON format and must not contain any newlines and must not start with ```json or end with ```. The first activity must be start city to target city, and the last one must be target city back to start city. The "tickets" should be equal to the num of people, and the "cars" if you use taxi should be equal to the num of (people+3)//4, the "cost" should be the cost per person or per car or per room. The "time" should be in the format "HH:MM" and the "transport" should be in ['walk', 'taxi', 'metro']. Not every meals is needed. It can be [breakfast, lunch, dinner] according to the time, not time arriving but time of eating. Even if arriving at 8:00 but having meals at 11:00 am will be lunch, skipping breakfast. Only use and follow the information provided!!! The train or airplane information must be exactlly the same as the provided data.
"""
    + output_format
    + "\n\n"
    + QA_STRING
    + "\n\n"
    + "The provided information and query are here:\n"
)
