import os
import pandas as pd
from pandas import DataFrame


def time2float(time_str):
    h, m = time_str.split(":")
    return int(h) + int(m) / 60


class IntercityTransport:
    def __init__(self, path: str = "../../database/intercity_transport/", en_version=False):
        file_suffix = "_en" if en_version else ""
        curdir = os.path.dirname(os.path.realpath(__file__))
        self.base_path = os.path.join(curdir, path)
        self.airplane_path = self.base_path + f"airplane{file_suffix}.jsonl"
        self.airplane_df = pd.read_json(
            self.airplane_path, lines=True, keep_default_dates=False
        )
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
        self.city_list = city_list
        self.city_en_list = [
            "shanghai", "beijing", "shenzhen", "guangzhou", "chongqing",
            "suzhou", "chengdu", "hangzhou", "wuhan", "nanjing",
        ]
        self.city_cn_to_en = dict(zip(self.city_list, self.city_en_list))
        self.city_en_to_cn = dict(zip(self.city_en_list, self.city_list))

        self.train_df_dict = {}

        for start_city in city_list:
            for end_city in city_list:
                if start_city == end_city:
                    continue
                train_path = (
                    self.base_path
                    + "train/"
                    + f"from_{start_city}_to_{end_city}{file_suffix}.json"
                )
                train_df = pd.read_json(train_path)
                self.train_df_dict[(start_city, end_city)] = train_df

    def select(
        self, start_city, end_city, intercity_type, earliest_leave_time="00:00"
    ) -> DataFrame:
        if start_city in self.city_en_to_cn:
            start_city = self.city_en_to_cn[start_city]
        if end_city in self.city_en_to_cn:
            end_city = self.city_en_to_cn[end_city]
        if intercity_type not in ["train", "airplane"]:
            return "only support intercity_type in ['train','airplane']"
        res = self._select(start_city, end_city, intercity_type)
        bool_list = [False] * len(res)
        for i in range(len(res)):
            if time2float(res.loc[i, "BeginTime"]) >= time2float(earliest_leave_time):
                bool_list[i] = True
        return res[bool_list]

    def _select(self, start_city, end_city, intercity_type) -> DataFrame:
        # intercity_type=='train' | 'airplane'
        if intercity_type == "airplane":

            if len(self.airplane_df) == 0:
                return None

            filtered_flights = self.airplane_df[
                (self.airplane_df["From"].str.contains(start_city))
                & (self.airplane_df["To"].str.contains(end_city))
            ]
            sorted_flights = filtered_flights.sort_values(by="BeginTime").reset_index(
                drop=True
            )
            return sorted_flights
        if intercity_type == "train":

            if len(self.train_df_dict[(start_city, end_city)]) == 0:
                return None

            filtered_trains = self.train_df_dict[(start_city, end_city)]
            sorted_trains = filtered_trains.sort_values(by="BeginTime").reset_index(
                drop=True
            )
            return sorted_trains


if __name__ == "__main__":
    a = IntercityTransport()
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
    city_en_list = [
        "shanghai",
        "beijing",
        "shenzhen",
        "guangzhou",
        "chongqing",
        "suzhou",
        "chengdu",
        "hangzhou",
        "wuhan",
        "nanjing",
    ]
    str_list = []
    for i in range(len(city_list)):
        for j in range(i + 1, len(city_list)):
            tmp_len = 0

            tmp = a.select(city_list[i], city_list[j], "train")
            if not isinstance(tmp, DataFrame):
                tmp_len = 0
            else:
                tmp_len = len(tmp)
            if tmp_len > 0:
                str_list.append(
                    "('{}','{}','{}',{})".format(
                        city_en_list[i], city_en_list[j], "train", tmp_len
                    )
                )

            tmp = a.select(city_list[j], city_list[i], "train")
            if not isinstance(tmp, DataFrame):
                tmp_len = 0
            else:
                tmp_len = len(tmp)
            if tmp_len > 0:
                str_list.append(
                    "('{}','{}','{}',{})".format(
                        city_en_list[j], city_en_list[i], "train", tmp_len
                    )
                )

            tmp = a.select(city_list[i], city_list[j], "flight")
            if not isinstance(tmp, DataFrame):
                tmp_len = 0
            else:
                tmp_len = len(tmp)
            if tmp_len > 0:
                str_list.append(
                    "('{}','{}','{}',{})".format(
                        city_en_list[i], city_en_list[j], "airplane", tmp_len
                    )
                )

            tmp = a.select(city_list[j], city_list[i], "flight")
            if not isinstance(tmp, DataFrame):
                tmp_len = 0
            else:
                tmp_len = len(tmp)
            if tmp_len > 0:
                str_list.append(
                    "('{}','{}','{}',{})".format(
                        city_en_list[j], city_en_list[i], "airplane", tmp_len
                    )
                )

    print(",\n".join(str_list))
