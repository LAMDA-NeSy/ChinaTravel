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

from chinatravel.environment.language import normalize_lang


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


def _resolve_local_query_paths(data_dir, split, query_ids, lang):
    preferred_names = [split]
    if lang == "en" and not split.endswith("_EN"):
        preferred_names.append(f"{split}_EN")
    preferred_dirs = [
        os.path.join(data_dir, name)
        for name in preferred_names
        if os.path.isdir(os.path.join(data_dir, name))
    ]
    for split_dir in preferred_dirs:
        paths = {
            query_id: os.path.join(split_dir, f"{query_id}.json")
            for query_id in query_ids
        }
        if all(os.path.isfile(path) for path in paths.values()):
            return paths
    if preferred_dirs:
        missing = {
            split_dir: [
                query_id
                for query_id in query_ids
                if not os.path.isfile(
                    os.path.join(split_dir, f"{query_id}.json")
                )
            ]
            for split_dir in preferred_dirs
        }
        raise ValueError(
            f"Split directory does not contain every configured UID: {missing}"
        )

    indexed_paths = {query_id: [] for query_id in query_ids}
    for directory_name in sorted(os.listdir(data_dir)):
        directory = os.path.join(data_dir, directory_name)
        if not os.path.isdir(directory):
            continue
        for query_id in query_ids:
            path = os.path.join(directory, f"{query_id}.json")
            if os.path.isfile(path):
                indexed_paths[query_id].append(path)

    missing = [
        query_id for query_id, paths in indexed_paths.items() if not paths
    ]
    ambiguous = {
        query_id: paths
        for query_id, paths in indexed_paths.items()
        if len(paths) > 1
    }
    if missing or ambiguous:
        raise ValueError(
            "Unable to resolve local split {!r}: missing={}, ambiguous={}".format(
                split,
                missing,
                ambiguous,
            )
        )
    return {
        query_id: paths[0] for query_id, paths in indexed_paths.items()
    }


def load_query_local(args, version="", verbose=False):
    query_data = {}
    lang = normalize_lang(getattr(args, "lang", None))

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
    if lang == "en":
        data_dir = os.path.join(data_dir, "en")

    query_paths = _resolve_local_query_paths(
        data_dir,
        args.splits,
        query_id_list,
        lang,
    )
    for query_id in query_id_list:
        with open(query_paths[query_id], encoding="utf-8") as query_file:
            data_i = json.load(query_file)
        if data_i.get("uid") != query_id:
            raise ValueError(
                f"Query UID mismatch for {query_paths[query_id]}: "
                f"expected {query_id!r}, got {data_i.get('uid')!r}"
            )
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
    lang = normalize_lang(getattr(args, "lang", None))
    if lang == "en":
        return load_query_local(args)

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
        if "hard_logic_py" in data_i:
            data_i["hard_logic_py"] = ast.literal_eval(data_i["hard_logic_py"])

    query_id_list = [data_i["uid"] for data_i in query_data]
    data_dict = {}
    for data_i in query_data:
        if not getattr(args, "oracle_translation", False):
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
argparser.add_argument("--lang", type=str, choices=["zh", "en"], default="zh")

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
