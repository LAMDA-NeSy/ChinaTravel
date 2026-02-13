import os
import json


class Poi:
    def __init__(self, base_path: str = "../../database/poi/", en_version=False):
        self.en_version = en_version
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
            os.path.join(curdir, f"{base_path}/{city}/poi{file_suffix}.json") for city in city_list
        ]
        self.data = {}
        for i, city in enumerate(city_list):
            self.data[city] = json.load(open(data_path_list[i], "r", encoding="utf-8"))
            city_data = {}
            for name_pos in self.data[city]:
                name = name_pos["name"]
                pos = name_pos["position"]
                city_data[name] = tuple(pos)
            self.data[city] = city_data
            # self.data[city] = [
            #     (x["name"], tuple(x["position"])) for x in self.data[city]
            # ]
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
        self.city_cn_list = city_cn_list
        self.city_list = city_list

    def search(self, city: str, name: str):
        if city in self.city_list:
            city = self.city_cn_list[self.city_list.index(city)]
        city_data = self.data[city]
        try:
            return city_data[name]
        except KeyError:
            if self.en_version:
                return f"No such point in the city. Check the point name: {name}."
            return f"城市中没有该地点，请检查地点名称: {name}."


def test():
    poi = Poi()
    while True:
        query = input("请输入查询的poi名称：")
        if query == "exit":
            return
        print(poi.search("南京", query))


if __name__ == "__main__":
    test()
