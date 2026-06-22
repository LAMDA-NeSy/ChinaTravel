import os
import json

project_root_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from chinatravel.environment.language import normalize_lang


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            import numpy as np
        except ImportError:
            np = None
        if np is None:
            return super(NpEncoder, self).default(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


DEFAULT_HUGGINGFACE_SPLITS = {
    "easy",
    "medium",
    "human",
    "preference_base50",
    "preference0_base50",
    "preference1_base50",
    "preference2_base50",
    "preference3_base50",
    "preference4_base50",
    "preference5_base50",
}
PREFERENCE_HUGGINGFACE_SPLITS = {
    "preference0_base50",
    "preference1_base50",
    "preference2_base50",
    "preference3_base50",
    "preference4_base50",
    "preference5_base50",
}
ORACLE_FIELDS = {"hard_logic", "hard_logic_py", "hard_logic_nl"}


def _strip_oracle_fields(data_i):
    for key in ORACLE_FIELDS:
        data_i.pop(key, None)
    return data_i


def _validate_query_record(data_i):
    if "hard_logic_py" in data_i and not isinstance(data_i["hard_logic_py"], list):
        raise ValueError(
            "Expected fixed ChinaTravel data where hard_logic_py is a list, "
            f"got {type(data_i['hard_logic_py']).__name__} for {data_i.get('uid', '<unknown>')}."
        )
    return data_i


def _load_huggingface_split(split):
    from datasets import load_dataset as hg_load_dataset

    config_name = "preference" if split in PREFERENCE_HUGGINGFACE_SPLITS else "default"
    return hg_load_dataset("LAMDA-NeSy/ChinaTravel", name=config_name)[split].to_list()


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
                    data_i = _validate_query_record(data_i)

                    if hasattr(args, 'oracle_translation') and not args.oracle_translation:
                        _strip_oracle_fields(data_i)

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

    if args.splits not in DEFAULT_HUGGINGFACE_SPLITS:
        return load_query_local(args)
    query_data = [_validate_query_record(data_i) for data_i in _load_huggingface_split(args.splits)]

    query_id_list = [data_i["uid"] for data_i in query_data]
    data_dict = {}
    for data_i in query_data:
        if not getattr(args, "oracle_translation", False):
            _strip_oracle_fields(data_i)

        data_dict[data_i["uid"]] = data_i

    return query_id_list, data_dict


if __name__ == "__main__":
    import argparse

    argparser = argparse.ArgumentParser()
    argparser.add_argument("--splits", type=str, default="easy")
    argparser.add_argument("--lang", type=str, choices=["zh", "en"], default="zh")

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
