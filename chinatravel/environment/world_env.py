import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append("../..")
from environment.tools import *
from pandas import DataFrame
from typing import Any


class EnvOutput:
    class KeyError(Exception):
        pass

    def __init__(self, success: bool, data: Any):
        self._success = success
        self._data = data
        if isinstance(data, DataFrame):
            self._page_idx = 0
            self._page_total = len(data) // 10 + (1 if len(data) % 10 != 0 else 0)
            self._original_data = data
            self._data = data.head(10)

    def __getitem__(self, key):
        if key == "success":
            return self._success
        if key == "data":
            return self._data
        if key == "whole_data":
            return (
                self._original_data if isinstance(self._data, DataFrame) else self._data
            )
        if key == "str":
            return str(self)
        raise self.KeyError(
            f"Invalid key: {key},only support 'success', 'data', 'whole_data' and 'str'."
        )

    def to_dict(self):
        return {
            "success": self._success,
            "data": self._data,
            "whole_data": (
                self._original_data if isinstance(self._data, DataFrame) else self._data
            ),
            "str": str(self),
        }

    def __str__(self):
        if isinstance(self._data, DataFrame):
            if len(self._data) == 0:
                return "No data."
            header_str = self._data.columns.values
            res = str(header_str) + "\n"
            for i in range(10):
                if i >= len(self._data):
                    break
                res += str(self._data.iloc[i].values) + "\n"
            res += (
                "Page/Total: " + str(self._page_idx + 1) + "/" + str(self._page_total)
            )
            return res
        return str(self._data)

    def next_page(self):
        if not isinstance(self._data, DataFrame):
            return (
                "next_page() is not supported for this data type:"
                + str(type(self._data))
                + "\nonly DataFrame support next_page()."
                + "\nMake sure you are using the correct index. -1 is the lastest result."
            )
        if (self._page_idx - 1) * 10 >= len(self._original_data):
            self._data = "No more data."

        self._page_idx += 1
        self._data = self._original_data.iloc[
            self._page_idx * 10 : (self._page_idx + 1) * 10
        ]
        return self


class WorldEnv:
    """
    World Environment
    Provide APIs to access the virtual world.
    """

    def __init__(self, en_version=False):
        """
        Initialize the world environment.
        """

        self.support_cities = [
            "上海",
            "北京",
            "深圳",
            "广州",
            "重庆",
            "苏州",
            "成都",
            "杭州",
            "武汉",
            "南京",
        ]
        self.attractions = Attractions(en_version=en_version)
        self.accommodations = Accommodations(en_version=en_version)
        self.restaurants = Restaurants(en_version=en_version)
        self.intercitytransport = IntercityTransport(en_version=en_version)
        self.transportation = Transportation(en_version=en_version)
        self.poi = Poi(en_version=en_version)

        self.results = []

    def __call__(self, cmd_str: str):
        """
        Call the API by command string in the format of python function call.
        """
        # init env to execute the command directly
        attractions_keys = self.attractions.keys
        attractions_types = self.attractions.get_type_list
        attractions_select = self.attractions.select
        attractions_id_is_open = self.attractions.id_is_open
        attractions_nearby = self.attractions.nearby

        accommodations_keys = self.accommodations.keys
        accommodations_select = self.accommodations.select
        accommodations_nearby = self.accommodations.nearby

        restaurants_select = self.restaurants.select
        restaurants_keys = self.restaurants.keys
        restaurants_nearby = self.restaurants.nearby
        restaurants_id_is_open = self.restaurants.id_is_open
        restaurants_cuisine = self.restaurants.get_cuisine_list
        restaurants_with_recommended_food = (
            self.restaurants.restaurants_with_recommended_food
        )

        goto = self.transportation.goto
        intercity_transport_select = self.intercitytransport.select
        poi_lat_lon_search = self.poi.search

        next_page = self.next_page
        Results = self.results

        try:
            res = eval(cmd_str)
            if not isinstance(res, EnvOutput):
                res = EnvOutput(True, res)
        except Exception as e:
            res = EnvOutput(False, "Invalid command.\n" + str(e))
        self.results.append(res)
        return self.results[-1]

    def next_page(self):
        """
        Go to the next page.
        """
        if len(self.results) == 0:
            return "No results."
        return self.results[-1].next_page()

    def reset(self):
        """
        Reset the environment.
        """
        self.results = []


__doc__ = """

This file provides an interface to access the virtual world environment.
You can use the WorldEnv as long as you instance WorldEnv class and call the APIs with the command string.
The command string should be in the format of python function call,

for example:
```python
test_env = WorldEnv()
print(test_env("attractions_keys('上海')"))
```

APIs for the World Environment:
(1) attractions_keys(city: str)
Description: Returns a list of (key, type) pairs of the attractions data.
Parameters: 
city: The city name.
(2) attractions_select(city: str, key: str, func: Callable):
Description: Returns a DataFrame with data filtered by the specified key with the specified function.
Parameters:
city: The city name.
key: The key column to filter, only one key can be used. If not specified, return all data.
func: The lambda function applied to the key column, must return a boolean value. Only apply to one key. If not specified, return all data.
(3) attractions_id_is_open(city: str, id: int, time: str):
Description: Returns whether the attraction with the specified ID is open at the specified time.
Parameters:
city: The city name.
id: The ID of the attraction.
time: The time to check, in the format 'HH:MM'.
(4) attractions_nearby(city: str, point: str, topk: int, dist: float):
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
(7) accommodations_select(city: str, key: str = "", func: Callable):
Description: Returns a DataFrame with data filtered by the specified key with the specified function.
Parameters: 
city: The city name.
key: The key column to filter, only one key can be used. If not specified, return all data.
func: The lambda function applied to the key column, must return a boolean value. Only apply to one key. If not specified, return all data.
(8) accommodations_nearby(city: str, point: str, topk: int, dist: float):
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
(10) restaurants_select(city: str, key: str = "", func: Callable):
Description: Returns a DataFrame with data filtered by the specified key with the specified function. 
city: The city name.
key: The key column to filter, only one key can be used. If not specified, return all data.
func: The lambda function applied to the key column, must return a boolean value. Only apply to one key. If not specified, return all data.
(11) restaurants_id_is_open(city: str, id: int, time: str):
Description: Returns whether the restaurant with the specified ID is open at the specified time and day.
Parameters: 
city: The city name.
id: The ID of the restaurant.
time: The time to check, in the format 'HH:MM'.
(12) restaurants_nearby(city: str, point: str, topk: int, dist: float):
Description: Returns the top K restaurants within the specified distance of the location.
Parameters: 
city: The city name.
point: The name of the location.
topk: The number of restaurants to return.
dist: The maximum distance from the location, default is 2.
(13) restaurants_restaurants_with_recommended_food(city: str, food: str):
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

(16) intercity_transport_select(start_city: str, end_city: str, intercity_type: str, earliest_leave_time: str = None):
Description: get the intercity transportation information between two cities. You need to call this function at least twice to get the transportation information between two locations for going and returning.
Parameters:
start_city: The start city name.
end_city: The end city name.
intercity_type: The type of intercity transportation, must in ['train', 'airplane'].
earliest_leave_time: The earliest leave time in the format 'HH:MM'.

(17) Results[index] Results[index].next_page()
Description: Get the result of the index or go to the next page of the result.
"""


if __name__ == "__main__":
    import random

    test_env = WorldEnv()
    test_env.transportation.goto(
        city="杭州",
        start="杭州东站",
        end="上海虹桥站",
        start_time="17:00",
        transport_type="metro",
    )

    def test_for_attractions(city_list):
        # test for attractions
        for city in city_list:
            print(f"Testing attractions in {city}...")
            keys = test_env(f"attractions_keys('{city}')")["data"]
            type_list = test_env(f"attractions_types('{city}')")["data"]
            for key, _ in keys:
                print(
                    test_env(f"attractions_select('{city}', '{key}', lambda x: True)")[
                        "data"
                    ]
                )
            original_data = None
            for type_ in type_list:
                original_data = test_env(
                    f"attractions_select('{city}', 'type', lambda x: x == '{type_}')"
                )["data"]
            name_list = original_data["name"].tolist()
            data_len = len(name_list)
            time_list = ["6:30", "12:00", "18:00", "23:00"]
            for i in range(3):
                index = random.randint(0, data_len - 1)
                print(
                    test_env(
                        f"attractions_id_is_open('{city}', {index}, '{random.choice(time_list)}')"
                    )["data"]
                )
                name = name_list[index]
                print(test_env(f"attractions_nearby('{city}', '{name}', 5, 2)")["data"])

    def test_for_accommodations(city_list):
        # test for accommodations
        for city in city_list:
            print(f"Testing accommodations in {city}...")
            keys = test_env(f"accommodations_keys('{city}')")["data"]
            for key, _ in keys:
                print(
                    test_env(
                        f"accommodations_select('{city}', '{key}', lambda x: True)"
                    )["data"]
                )
            original_data = test_env(
                f"accommodations_select('{city}', 'name', lambda x: True)"
            )["data"]
            name_list = original_data["name"].tolist()
            data_len = len(name_list)
            for i in range(3):
                index = random.randint(0, data_len - 1)
                name = name_list[index]
                print(
                    test_env(f"accommodations_nearby('{city}', '{name}', 5, 2)")["data"]
                )

    def test_for_restaurants(city_list):
        # test for restaurants
        for city in city_list:
            print(f"Testing restaurants in {city}...")
            keys = test_env(f"restaurants_keys('{city}')")["data"]
            cuisine_list = test_env(f"restaurants_cuisine('{city}')")["data"]
            for key, _ in keys:
                print(
                    test_env(f"restaurants_select('{city}', '{key}', lambda x: True)")[
                        "data"
                    ]
                )
            original_data = test_env(
                f"restaurants_select('{city}', 'name', lambda x: True)"
            )["data"]
            name_list = original_data["name"].tolist()
            data_len = len(name_list)
            time_list = ["6:30", "12:00", "18:00", "23:00"]
            for i in range(3):
                index = random.randint(0, data_len - 1)
                test_env.restaurants.id_is_open(city, index, random.choice(time_list))
                print(
                    test_env(
                        f"restaurants_id_is_open('{city}', {index}, '{random.choice(time_list)}')"
                    )["data"]
                )
                name = name_list[index]
                print(test_env(f"restaurants_nearby('{city}', '{name}', 5, 2)")["data"])
            food_list = ["烤鸭"]
            for food in food_list:
                print(food)
                print(
                    test_env(
                        f"restaurants_restaurants_with_recommended_food('{city}', '{food}')"
                    )["data"]
                )

    def test_for_goto(city_list):
        # test for goto
        for city in city_list:
            print(f"Testing goto in {city}...")
            name_list = test_env(
                f"attractions_select('{city}', 'name', lambda x: True)"
            )["data"]["name"].tolist()
            start = random.choice(name_list)
            end = random.choice(name_list)
            test_env.transportation.goto(city, start, end, "12:00", "walk")
            test_env.transportation.goto(city, start, end, "12:00", "taxi")
            test_env.transportation.goto(city, start, end, "12:00", "metro")
            print(test_env(f"goto('{city}', '{start}', '{end}', '12:00', 'walk')"))
            print(test_env(f"goto('{city}', '{start}', '{end}', '12:00', 'taxi')"))
            print(test_env(f"goto('{city}', '{start}', '{end}', '12:00', 'metro')"))

    def test_for_intercity_transport(city_list):
        # test for intercity transport
        for i in range(len(city_list)):
            for j in range(i + 1, len(city_list)):
                print(
                    test_env(
                        f"intercity_transport_select('{city_list[i]}', '{city_list[j]}', 'train')"
                    )["data"]
                )
                print(
                    test_env(
                        f"intercity_transport_select('{city_list[i]}', '{city_list[j]}', 'airplane')"
                    )["data"]
                )
                print(
                    test_env(
                        f"intercity_transport_select('{city_list[i]}', '{city_list[j]}', 'train', '12:00')"
                    )
                )

    def test_for_next_page():
        print(
            test_env("attractions_select('上海', 'type', lambda x: True)")["whole_data"]
        )
        print(test_env("attractions_select('上海', 'type', lambda x: True)"))
        print(test_env("next_page()"))
        print(test_env("next_page()"))

    def test_all():
        city_list = [
            "上海",
            "北京",
            "深圳",
            "广州",
            "重庆",
            "苏州",
            "成都",
            "杭州",
            "武汉",
            "南京",
        ]
        city_list = ["上海"]
        # 随机选取一个城市
        # city_list = random.sample(city_list, 1)
        test_for_attractions(city_list)
        test_for_accommodations(city_list)
        test_for_restaurants(city_list)
        test_for_goto(city_list)
        test_for_intercity_transport(city_list)
        test_for_next_page()

    test_all()
