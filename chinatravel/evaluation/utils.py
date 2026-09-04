import json
import jsonschema
from jsonschema import validate
import os
import pandas as pd

project_root_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from chinatravel.agent.utils import Logger, NpEncoder
from chinatravel.environment.tools import Attractions


class AttractionsOODTag(Attractions):
    def __init__(
        self, base_path: str = os.path.dirname(__file__) + "/eval_annotation/attractions/", en_version=False
    ):
        super().__init__(en_version=en_version)
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
        self.ood_tag = {}
        for city in city_list:
            self.ood_tag[city] = pd.read_csv(
                os.path.join(curdir, f"{base_path}/{city}/attractions_tag.csv")
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
            self.ood_tag[city_cn_list[i]] = self.ood_tag.pop(city)
        for city in city_cn_list:
            self.data[city] = pd.merge(
                self.data[city], self.ood_tag[city], on=["id", "name"], how="left"
            )
            # print(self.data[city])
        del self.ood_tag

def load_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_json(json_data, schema):
    try:
        validate(instance=json_data, schema=schema)
        return True
    except jsonschema.exceptions.ValidationError as e:
        return False
    
def save_json_file(json_data, file_path):
    with open(file_path, "w", encoding="utf8") as dump_f:
        json.dump(json_data, dump_f, ensure_ascii=False, indent=4,  cls=NpEncoder)



if __name__ == "__main__":
    schema_file_path = "./output_schema.json"
    json_file_path_template = "../results/test_20240909091404/query_{}_result.json"

    schema = load_json_file(schema_file_path)
    acc = 0
    for i in range(10):
        try:
            json_data = load_json_file(json_file_path_template.format(i))
            if validate_json(json_data, schema):
                acc += 1
            else:
                print("Error {}".format(i))
        except:
            print("Error {}".format(i))
            continue
    print(acc / 10)
    a = AttractionsOODTag()
    print(a.select("北京", "id", lambda x: x == 1))
    print(a.select("北京", "name", lambda x: x == "故宫博物院"))
