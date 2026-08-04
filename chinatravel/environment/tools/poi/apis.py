import os
import json
from chinatravel.environment.language import CITY_SLUGS, city_names, normalize_lang, relative_database_path


class Poi:
    def __init__(self, base_path: str = None, en_version=False, lang=None):

        self.lang = normalize_lang(lang, en_version=en_version)
        if base_path is None:
            base_path = relative_database_path(self.lang, "poi")
        city_list = CITY_SLUGS
        curdir = os.path.dirname(os.path.realpath(__file__))
        data_path_list = [
            os.path.join(curdir, f"{base_path}/{city}/poi.json") for city in city_list
        ]
        self.data = {}
        for i, city in enumerate(city_list):
            with open(data_path_list[i], "r", encoding="utf-8") as file:
                self.data[city] = json.load(file)
            city_data = {}
            for name_pos in self.data[city]:
                name = name_pos["name"]
                pos = name_pos["position"]
                city_data[name] = tuple(pos)
            self.data[city] = city_data
            # self.data[city] = [
            #     (x["name"], tuple(x["position"])) for x in self.data[city]
            # ]
        city_cn_list = city_names(self.lang)
        for i, city in enumerate(city_list):
            self.data[city_cn_list[i]] = self.data.pop(city)
        self.city_cn_list = city_cn_list
        self.city_list = city_list

    def search(self, city: str, name: str):
        city_key = city.lower() if isinstance(city, str) else city
        if city_key in self.city_list:
            city = self.city_cn_list[self.city_list.index(city_key)]
        city_data = self.data[city]
        try:
            return city_data[name]
        except KeyError:
            return f"No such point in the city. Check the point name: {name}."


def test():
    poi = Poi()
    while True:
        query = input("请输入查询的poi名称：")
        if query == "exit":
            return
        print(poi.search("南京", query))


if __name__ == "__main__":
    test()
