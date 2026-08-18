import pandas as pd
from pandas import DataFrame
from typing import Callable
import os
from geopy.distance import geodesic

import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from poi.apis import Poi
from chinatravel.environment.language import CITY_SLUGS, city_names, normalize_lang, relative_database_path


class Restaurants:
    def __init__(self, base_path: str = None, lang=None):
        self.lang = normalize_lang(lang)
        if base_path is None:
            base_path = relative_database_path(self.lang, "restaurants")
        city_list = CITY_SLUGS
        self.data = {}
        curdir = os.path.dirname(os.path.realpath(__file__))
        for city in city_list:
            path = os.path.join(curdir, base_path, city, "restaurants_" + city + ".csv")
            self.data[city] = pd.read_csv(path)

        self.key_type_tuple_list_map = {}
        for city in city_list:
            self.key_type_tuple_list_map[city] = []
            for key in self.data[city].keys():
                self.key_type_tuple_list_map[city].append(
                    (key, type(self.data[city][key][0]))
                )
        self.cuisine_list_map = {}
        for city in city_list:
            self.cuisine_list_map[city] = self.data[city]["cuisine"].unique()
        city_cn_list = city_names(self.lang)

        for i, city in enumerate(city_list):
            self.data[city_cn_list[i]] = self.data.pop(city)
            self.key_type_tuple_list_map[city_cn_list[i]] = (
                self.key_type_tuple_list_map.pop(city)
            )
            self.cuisine_list_map[city_cn_list[i]] = self.cuisine_list_map.pop(city)

        self.poi = Poi(lang=self.lang)

    def keys(self, city: str):
        return self.key_type_tuple_list_map[city]

    def select(self, city: str, key, func: Callable) -> DataFrame:
        if key not in self.data[city].keys():
            return "Key not found."
        bool_list = [func(x) for x in self.data[city][key]]
        return self.data[city][bool_list]

    def id_is_open(self, city: str, id: int, time: str) -> bool:
        match = self.data[city].loc[self.data[city]["id"] == id]
        open_time = match["opentime"].values[0]
        end_time = match["endtime"].values[0]
        open_time = (
            -1
            if open_time == "不营业"
            else float(open_time.split(":")[0]) + float(open_time.split(":")[1]) / 60
        )
        end_time = (
            -1
            if end_time == "不营业"
            else float(end_time.split(":")[0]) + float(end_time.split(":")[1]) / 60
        )
        time = float(time.split(":")[0]) + float(time.split(":")[1]) / 60
        if open_time == -1 or end_time == -1:
            return False
        if open_time < end_time:
            return open_time <= time <= end_time
        else:
            return open_time <= time or time <= end_time

    def nearby(self, city: str, point: str, topk: int = None, dist=2) -> DataFrame:
        lat_lon = self.poi.search(city, point)
        if isinstance(lat_lon, str):
            return lat_lon
        lat, lon = lat_lon
        distance = [
            geodesic((lat, lon), (x, y)).km
            for x, y in zip(self.data[city]["lat"], self.data[city]["lon"])
        ]
        tmp = self.data[city].copy()
        tmp["distance"] = distance
        tmp = tmp.sort_values(by=["distance"])
        if topk is None:
            return tmp[tmp["distance"] <= dist]
        return tmp[tmp["distance"] <= dist].head(topk)

    def restaurants_with_recommended_food(self, city: str, food: str):
        return self.data[city][self.data[city]["recommendedfood"].str.contains(food)]

    def get_cuisine_list(self, city: str):
        return self.cuisine_list_map[city]


if __name__ == "__main__":
    a = Restaurants()
