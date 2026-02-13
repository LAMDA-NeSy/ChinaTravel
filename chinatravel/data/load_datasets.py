import sys
import os
import json
import numpy as np
from datasets import load_dataset as hg_load_dataset
import ast

project_root_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

if project_root_path not in sys.path:
    sys.path.insert(0, project_root_path)


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


def _get_language(args):
    return getattr(args, "lang", "zh")


def _normalize_query_language(data_i, lang):
    if lang == "zh":
        return data_i

    key_pairs = [
        ("nature_language", "nature_language_en"),
        ("hard_logic", "hard_logic_en"),
        ("hard_logic_py", "hard_logic_py_en"),
        ("hard_logic_nl", "hard_logic_nl_en"),
        ("preference", "preference_en"),
    ]
    for base_key, lang_key in key_pairs:
        if lang_key in data_i:
            data_i[base_key] = data_i[lang_key]
    return data_i


def load_query_local(args, version="", verbose=False):
    query_data = {}

    # split_config_file = 'default_splits/{}.txt'.format(args.splits)

    split_config_file = os.path.join(
        project_root_path,
        "chinatravel",
        "evaluation",
        "default_splits",
        "{}.txt".format(args.splits),
    )

    print("config file for testing split: {}".format(split_config_file))

    query_id_list = []
    with open(split_config_file, "r") as f:
        for line in f.readlines():
            line = line.strip()
            query_id_list.append(line)

    if verbose:
        print(query_id_list)

    data_dir = os.path.join(project_root_path, "chinatravel", "data")

    dir_list = os.listdir(data_dir)
    for dir_i in dir_list:
        dir_ii = os.path.join(data_dir, dir_i)
        if os.path.isdir(dir_ii):
            file_list = os.listdir(dir_ii)

            for file_i in file_list:
                query_id = file_i.split(".")[0]
                if query_id in query_id_list:
                    data_i = json.load(
                        open(os.path.join(dir_ii, file_i), encoding="utf-8")
                    )

                    data_i = _normalize_query_language(data_i, _get_language(args))

                    if hasattr(args, 'oracle_translation') and not args.oracle_translation:
                        if "hard_logic" in data_i:
                            del data_i["hard_logic"]
                        if "hard_logic_py" in data_i:
                            del data_i["hard_logic_py"]
                        if "hard_logic_nl" in data_i:
                            del data_i["hard_logic_nl"]

                    query_data[query_id] = data_i

    # print(query_data)

    if verbose:
        for query_id in query_id_list:
            print(query_id, query_data[query_id])

    return query_id_list, query_data


def load_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(json_data, file_path):
    with open(file_path, "w", encoding="utf8") as dump_f:
        json.dump(json_data, dump_f, ensure_ascii=False, indent=4, cls=NpEncoder)



def load_query(args):
    
    if not args.splits in ["easy", "medium", "human", "preference_base50",
                           "preference0_base50", "preference1_base50", "preference2_base50",
                           "preference3_base50", "preference4_base50", "preference5_base50"]:
        return load_query_local(args)
    config_name = "default"
    if args.splits in ["preference0_base50", "preference1_base50", "preference2_base50",
                       "preference3_base50", "preference4_base50", "preference5_base50"]:
        config_name = "preference"
    # elif args.splits in ["human"]:
    #     config_name = "validation"
    # elif args.splits in ["human1000"]:
    #     config_name = "test"
    query_data = hg_load_dataset("LAMDA-NeSy/ChinaTravel", name=config_name)[args.splits].to_list()
    

    for data_i in query_data:
        data_i = _normalize_query_language(data_i, _get_language(args))
        if "hard_logic_py" in data_i and isinstance(data_i["hard_logic_py"], str):
            data_i["hard_logic_py"] = ast.literal_eval(data_i["hard_logic_py"])
    
    query_id_list = [data_i["uid"] for data_i in query_data]
    data_dict = {}
    for data_i in query_data:
        if not args.oracle_translation:
            if "hard_logic" in data_i:
                del data_i["hard_logic"]
            if "hard_logic_py" in data_i:
                del data_i["hard_logic_py"]
            if "hard_logic_nl" in data_i:
                del data_i["hard_logic_nl"]

        data_dict[data_i["uid"]] = data_i

    return query_id_list, data_dict


import argparse
argparser = argparse.ArgumentParser()
argparser.add_argument("--splits", type=str, default="easy")

if __name__ == "__main__":


    # from datasets import load_dataset as hg_load_dataset

    # # Login using e.g. `huggingface-cli login` to access this dataset
    # ds = hg_load_dataset("LAMDA-NeSy/ChinaTravel")
    # print(ds)
    # print(ds["easy"].to_list())

    # exit(0)
    args = argparser.parse_args()
    query_id_list, query_data = load_query(args)
    # print(query_id_list)
    # print(query_data)

    for uid in query_id_list:
        if uid in query_data:
            print(uid, query_data[uid])
        else:
            raise ValueError(f"{uid} not in query_data")
    
