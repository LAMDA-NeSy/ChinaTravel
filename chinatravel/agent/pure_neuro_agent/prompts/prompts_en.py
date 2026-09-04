# -*- coding: utf-8 -*-
import json
from .examples_en import EXAMPLE

import os

cur_dir = os.path.dirname(os.path.abspath(__file__))

example_query_path = os.path.join(cur_dir, "query_en.json")
example_plan_path = os.path.join(cur_dir, "plan_en.json")


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



ONESHOT_REACT_INSTRUCTION = (
    """Collect information for a query plan using interleaving 'Thought', 'Action', and 'Observation' steps. Ensure you gather valid information related to transportation, dining, attractions, and accommodation. All information including time, cost, location and others must be written in notebook, which will then be input into the Planner tool. Note that transportation bwteen locations must be written in notebook before planning. Note that the nested use of tools is not allowed, 'Thought' can reason about the current situation, and 'Action' can have 19 different types:

city_list = ["Shanghai", "Beijing", "Shenzhen", "Guangzhou", "Chongqing", "Suzhou", "Chengdu", "Hangzhou", "Wuhan", "Nanjing"]. All the cities name you use must be in this list.
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


DIRECT_PROMPT = (
    """You are a proficient planner. Based on the provided information and query, please give me a detailed plan. Note that all the information in your plan should be derived from the provided data. You must adhere to the format given in the schema. Your plan should be in JSON format and must not contain any newlines and must not start with ```json or end with ```. The first activity must be start city to target city, and the last one must be target city back to start city. The "tickets" should be equal to the num of people, and the "cars" if you use taxi should be equal to the num of (people+3)//4, the "cost" should be the cost per person or per car or per room. The "time" should be in the format "HH:MM" and the "transport" should be in ['walk', 'taxi', 'metro']. Not every meals is needed. It can be [breakfast, lunch, dinner] according to the time, not time arriving but time of eating. Even if arriving at 8:00 but having meals at 11:00 am will be lunch, skipping breakfast. Only use and follow the information provided!!! The train or airplane information must be exactlly the same as the provided data.
"""
    + output_format
    + "\n\n"
    + QA_STRING
    + "\n\n"
    + "The provided information and query are here:\n"
)
