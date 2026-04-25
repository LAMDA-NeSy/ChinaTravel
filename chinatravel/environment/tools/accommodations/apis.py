import pandas as pd
from pandas import DataFrame
from typing import Callable
from geopy.distance import geodesic
import os

import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from poi.apis import Poi


class Accommodations:

    def __init__(
        self, base_path: str = "../../database/accommodations/", en_version=False
    ):
        file_suffix = "_en" if en_version else ""
        curdir = os.path.dirname(os.path.realpath(__file__))
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
        data_path_list = [
            os.path.join(curdir, f"{base_path}/{city}/accommodations{file_suffix}.csv")
            for city in city_list
        ]
        self.data = {}
        for i, city in enumerate(city_list):
            self.data[city] = pd.read_csv(data_path_list[i]).dropna()
        self.key_type_tuple_list = {}
        for city in city_list:
            self.key_type_tuple_list[city] = []
            for key in self.data[city].keys():
                self.key_type_tuple_list[city].append(
                    (key, type(self.data[city].iloc[0][key]))
                )
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
            self.key_type_tuple_list[city_cn_list[i]] = self.key_type_tuple_list[city]

        self.poi = Poi(en_version=en_version)

    def keys(self, city):
        return self.key_type_tuple_list[city]

    def select(self, city, key, func: Callable) -> DataFrame:
        if key not in self.data[city].keys():
            return "Key not found."
        bool_list = [func(x) for x in self.data[city][key]]
        return self.data[city][bool_list]

    def nearby(self, city, point: str, topk: int = None, dist: float = 5) -> DataFrame:
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
        if dist is not None:
            tmp = tmp[tmp["distance"] < dist]
        tmp = tmp.sort_values(by=["distance"])
        if topk is not None:
            return tmp.head(topk)
        return tmp


if __name__ == "__main__":

    AccommodationsAPI = Accommodations()
    print(AccommodationsAPI.keys("南京"))

    # def query_key(key):
    #     print("query key {}".format(key))
    #     print(AccommodationsAPI.get_info(key))

    # for key in ["Price", "numBed", "hotelName"]:
    #     query_key(key)

    # def query_nearby(lat=32.040158, lon=118.823291):

    #     print("query nearby ({}, {}): ".format(lat, lon))
    #     print(AccommodationsAPI.nearby(lat=lat, lon=lon, topk=None, dist=2))

    # query_nearby()

    # print(AccommodationsAPI.select("numBed", 2))

    # print(AccommodationsAPI.data['featureHotelType'].unique())
