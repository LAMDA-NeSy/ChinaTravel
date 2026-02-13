import pandas as pd
from pandas import DataFrame
from typing import Callable
import os
from geopy.distance import geodesic

import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from poi.apis import Poi


class Attractions:
    def __init__(
        self,
        base_path: str = "../../database/attractions",
        en_version=False,
    ):
        file_suffix = "_en" if en_version else ""
        city_list = [
            "beijing",
            "shanghai",
            "nanjing",
            "suzhou",
            "hangzhou",
            "shenzhen",
            "chengdu",
            "wuhan",
            "guangzhou",
            "chongqing",
        ]
        curdir = os.path.dirname(os.path.realpath(__file__))
        data_path_list = [
            os.path.join(curdir, f"{base_path}/{city}/attractions{file_suffix}.csv")
            for city in city_list
        ]

        self.data = {}
        for i, city in enumerate(city_list):
            self.data[city] = pd.read_csv(data_path_list[i])
        self.key_type_tuple_list_map = {}
        for city in city_list:
            self.key_type_tuple_list_map[city] = []
            for key in self.data[city].keys():
                self.key_type_tuple_list_map[city].append(
                    (key, type(self.data[city][key][0]))
                )
        self.type_list_map = {}
        for city in city_list:
            self.type_list_map[city] = self.data[city]["type"].unique()
        city_cn_list = [
            "北京",
            "上海",
            "南京",
            "苏州",
            "杭州",
            "深圳",
            "成都",
            "武汉",
            "广州",
            "重庆",
        ]

        for i, city in enumerate(city_list):
            self.data[city_cn_list[i]] = self.data[city]
            self.key_type_tuple_list_map[city_cn_list[i]] = self.key_type_tuple_list_map[city]
            self.type_list_map[city_cn_list[i]] = self.type_list_map[city]

        self.poi = Poi(en_version=en_version)

    def keys(self, city: str):
        return self.key_type_tuple_list_map[city]

    def select(self, city: str, key, func: Callable) -> DataFrame:
        if key not in self.data[city].keys():
            return "Key not found."
        bool_list = [func(x) for x in self.data[city][key]]
        return self.data[city][bool_list]

    def id_is_open(self, city: str, id: int, time: str) -> bool:
        # open_time = self.data[city]["opentime"][id]
        # end_time = self.data[city]["endtime"][id]

        match = self.data[city].loc[self.data[city]["id"] == id]
        open_time = match["opentime"].values[0]
        end_time = match["endtime"].values[0]

        open_time = float(open_time.split(":")[0]) + float(open_time.split(":")[1]) / 60
        end_time = float(end_time.split(":")[0]) + float(end_time.split(":")[1]) / 60
        time = float(time.split(":")[0]) + float(time.split(":")[1]) / 60
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

    def get_type_list(self, city: str):
        return self.type_list_map[city]


if __name__ == "__main__":
    a = Attractions()
    print(a.get_type_list("南京"))
    # print(a.data)
    # print(a.get_info("Name"))
    # info_list, _ = a.get_info("Name")
    # print(a.get_info_for_index(info_list, 0))
    # print(a.get_info_for_index(info_list, [0, 1]))
    # print(a.nearby(a.data.iloc[0]['Latitude'], a.data.iloc[0]['Longitude']))
    # print(a.select("Name", "夫子庙"))
    # print(a.id_is_open(0, "10:00"))
    # print(a.select('Type', lambda x: x == '公园'))
    # print(a.data)
