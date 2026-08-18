import pandas as pd
from pandas import DataFrame
from typing import Callable
from geopy.distance import geodesic
import os

import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from poi.apis import Poi
from chinatravel.environment.language import CITY_SLUGS, city_names, normalize_lang, relative_database_path


class Accommodations:

    def __init__(self, base_path: str = None, en_version=False, lang=None):
        self.lang = normalize_lang(lang, en_version=en_version)
        if base_path is None:
            base_path = relative_database_path(self.lang, "accommodations")
        curdir = os.path.dirname(os.path.realpath(__file__))
        city_list = CITY_SLUGS
        data_path_list = [
            os.path.join(curdir, f"{base_path}/{city}/accommodations.csv")
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
        city_cn_list = city_names(self.lang)

        for i, city in enumerate(city_list):
            self.data[city_cn_list[i]] = self.data.pop(city)
            self.key_type_tuple_list[city_cn_list[i]] = self.key_type_tuple_list.pop(
                city
            )

        self.poi = Poi(lang=self.lang)

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
