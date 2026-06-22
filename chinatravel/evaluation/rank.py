import os
import time

project_root_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


class CompareError(Exception):
    pass


preference_list = [
    "convenient transportation",
    "convenient restaurants",
    "close to poi",
    "less walk",
    "more cost on meals",
    "more cost on hotel",
    "more cost on attractions",
    "less cost on meals",
    "less cost on hotel",
    "less cost on attractions",
    "less total cost",
    "easy trip",
    "more attractions",
    "more indoor attractions",
    "more outdoor attractions",
    "more popular attractions",
    "more unpopular attractions",
]
min_best_list = [
    "convenient_transport",
    "convenient_restaurant",
    "close_to_poi",
    "less_walk",
    "less cost on meals",
    "less cost on hotel",
    "less cost on attractions",
    "less total cost",
]

max_best_list = [
    "more cost on meals",
    "more cost on hotel",
    "more cost on attractions",
    "easy trip",
    "more attractions",
    "more indoor attractions",
    "more outdoor attractions",
    "more popular attractions",
    "more unpopular attractions",
]

func_result_name_list = [
    "convenient_transport",
    "convenient_restaurant",
    "near_poi",
    "less_walk",
    "meal_cost_ratio",
    "accommodation_cost_ratio",
    "attraction_cost_ratio",
    "total_cost",
    "attraction_satisfaction",
    "attraction_count",
    "indoor_attraction_ratio",
    "popular_attraction_ratio",
]


def get_funcname_by_preference(preference: str):
    if preference == "convenient transportation":
        return "convenient_transport"
    elif preference == "convenient restaurants":
        return "convenient_restaurant"
    elif preference == "close to poi" or preference == "close to":
        return "near_poi"
    elif preference == "less walk":
        return "less_walk"
    elif preference == "more cost on meals":
        return "meal_cost_ratio"
    elif preference == "more cost on hotel":
        return "accommodation_cost_ratio"
    elif preference == "more cost on attractions":
        return "attraction_cost_ratio"
    elif preference == "less cost on meals":
        return "meal_cost_ratio"
    elif preference == "less cost on hotel":
        return "accommodation_cost_ratio"
    elif preference == "less cost on attractions":
        return "attraction_cost_ratio"
    elif preference == "less total cost":
        return "total_cost"
    elif preference == "easy trip":
        return "attraction_satisfaction"
    elif preference == "more attractions":
        return "attraction_count"
    elif preference == "more indoor attractions":
        return "indoor_attraction_ratio"
    elif preference == "more outdoor attractions":
        return "indoor_attraction_ratio"
    elif preference == "more popular attractions":
        return "popular_attraction_ratio"
    elif preference == "more unpopular attractions":
        return "popular_attraction_ratio"
    else:
        raise CompareError("No such preference {}".format(preference))


def get_rank_with_value(value_list, best_type: str):
    import pandas as pd

    pandas_data = pd.Series(value_list)
    if best_type == "max":
        worst_value = min(pandas_data) - 1
        for meta_data in pandas_data:
            if meta_data == -1:
                meta_data = worst_value
        rank = pandas_data.rank(ascending=False, method="min")
    elif best_type == "min":
        worst_value = max(pandas_data) + 1
        for meta_data in pandas_data:
            if meta_data == -1:
                meta_data = worst_value
        rank = pandas_data.rank(ascending=True, method="min")
    else:
        raise CompareError("best_type should be 'max' or 'min'")
    return rank.tolist()


def load_query(query_id_list):
    from chinatravel.evaluation.utils import load_json_file

    query_data = {}
    data_dir = os.path.join(project_root_path, "chinatravel/data")
    data_dir_list = os.listdir(data_dir)
    for dir in data_dir_list:
        split_dir_path = os.path.join(data_dir, dir)
        if not os.path.isdir(split_dir_path):
            continue
        file_list = os.listdir(split_dir_path)
        for file in file_list:
            query_id = file.split(".")[0]
            if query_id in query_id_list:
                query_data[query_id] = load_json_file(os.path.join(data_dir, dir, file))
    return query_data


def rank(method_list, split_list):
    import pandas as pd

    # load query data
    for split in split_list:
        query_id_list = []
        query_id_list_file_path = os.path.join("./default_splits", f"{split}.txt")
        with open(query_id_list_file_path, "r") as f:
            for line in f.readlines():
                query_id_list.append(line.strip())
    queries = load_query(query_id_list)

    # load result data
    results = {}
    for query_id in query_id_list:
        results[query_id] = {}
    for split in split_list:
        for method in method_list:
            preference_results_path = os.path.join(
                project_root_path,
                "chinatravel",
                "eval/eval_res",
                f"splits_{split}",
                method,
                "preference.csv",
            )
            preference_results = pd.read_csv(preference_results_path).to_dict(
                orient="records"
            )
            for preference_result in preference_results:
                query_id = preference_result["data_id"]
                results[query_id][method] = preference_result

    # rank
    rank_result = []
    for method in method_list:
        rank_result.append({"method": method})
        for preference in preference_list:
            rank_result[-1][preference] = []
        rank_result[-1]["avg"] = -1

    for query_id in query_id_list:
        for preference in preference_list:
            if preference == "close to poi":
                flag = False
                for preference_en in queries[query_id]["preference_en"]:
                    if "close to" in preference_en:
                        flag = True
                        break
                if not flag:
                    continue
            elif not preference in queries[query_id]["preference_en"]:
                continue
            value_list = []
            for method in method_list:
                if preference == "convenient transportation":
                    print(query_id)
                    print(
                        f"method: {method}, value: {results[query_id][method][get_funcname_by_preference(preference)]}"
                    )
                value_list.append(
                    results[query_id][method][get_funcname_by_preference(preference)]
                )
            rank_list = get_rank_with_value(
                value_list, "max" if preference in max_best_list else "min"
            )
            for i, method in enumerate(method_list):
                rank_result[i][
                    preference if "close to" not in preference else "close to poi"
                ].append(rank_list[i])

    for i, method in enumerate(method_list):
        avg = 0
        num = 0
        for preference in preference_list:
            if len(rank_result[i][preference]) == 0:
                print(f"no data for {method} {preference}")
                rank_result[i][preference] = -1
                continue
            avg += sum(rank_result[i][preference])
            num += len(rank_result[i][preference])
            rank_result[i][preference] = sum(rank_result[i][preference]) / len(
                rank_result[i][preference]
            )
        rank_result[i]["avg"] = avg / num
    rank_result = pd.DataFrame(rank_result)
    return rank_result


if __name__ == "__main__":
    import argparse

    from chinatravel.agent.load_model import build_method_name, resolve_llm_name

    parser = argparse.ArgumentParser()
    parser.add_argument("--splits", "-s", type=str, default="preference")
    parser.add_argument(
        "--methods",
        "-m",
        type=str,
        default="",
        help="Comma-separated result directory names to rank.",
    )
    parser.add_argument(
        "--llm",
        "-l",
        type=str,
        default=None,
        help="Model name used to derive default method names when --methods is omitted.",
    )
    parser.add_argument("--lang", "--locale", choices=["zh", "en"], default="zh")
    args = parser.parse_args()

    if args.methods:
        method_list = [method.strip() for method in args.methods.split(",") if method.strip()]
    else:
        resolved_llm_name = resolve_llm_name(args.llm)
        if not resolved_llm_name:
            parser.error(
                "--methods is required unless --llm or CHINATRAVEL_OPENAI_MODEL/OPENAI_MODEL is set."
            )
        method_list = [
            build_method_name("LLMNeSy", resolved_llm_name, lang=args.lang),
            build_method_name("ReAct", resolved_llm_name, lang=args.lang),
            build_method_name("ReAct0", resolved_llm_name, lang=args.lang),
            build_method_name("TPCAgent", resolved_llm_name, lang=args.lang),
        ]
    split_list = [split.strip() for split in args.splits.split(",") if split.strip()]
    rank_res = rank(method_list, split_list)
    print(rank_res)
    file_name = f"rank_{time.strftime('%Y%m%d%H%M%S')}.csv"
    file_path = os.path.join(
        project_root_path, "chinatravel", "eval", "rank_preference", file_name
    )
    rank_res.to_csv(file_path, index=False)
