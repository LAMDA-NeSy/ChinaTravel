
import argparse

import os
import json

project_root_path = os.path.dirname(os.path.abspath(__file__))

DEFAULT_ATTRACTION_PR="""
attraction_count = 0
for activity in allactivities(plan):
    if activity_type(activity) == 'attraction':
        attraction_count += 1
result=attraction_count/(4*day_count(plan))
"""


DEFAULT_TRANS_PR="""
time_cost = 0
transport_count = 0
for activity in allactivities(plan):
    transports = activity_transports(activity)
    if transports!=[]:
        transport_count += 1
        time_cost += innercity_transport_time(transports)
if transport_count > 0:
    average_time_cost = time_cost / transport_count
    result= (-1/105) * average_time_cost + 8/7
else:
    result=0
"""
DEFAULT_RES_PR="""
res_count=0
for activity in allactivities(plan):
    if activity_type(activity) in ['breakfast', 'lunch', 'dinner']:
        res_count+=1
res_count=res_count/(day_count(plan))
result=res_count/3
"""
DEFAULT_PR=[
    DEFAULT_ATTRACTION_PR,
    DEFAULT_TRANS_PR,
    DEFAULT_RES_PR
]

def cal_default_pr_score(query_index, query_data, result_data,all_pass_id):
    import numpy as np
    from copy import deepcopy

    from tqdm import tqdm

    from chinatravel.symbol_verification.concept_func import func_dict
    from chinatravel.symbol_verification.dsl import execute_dsl_code

    all_score=[]
    def clamp(value):
        return max(0.0, min(1.0, value))

    for ii, idx in enumerate(tqdm(query_index)):
        symbolic_input, plan = query_data[idx], result_data[idx]
        results = []
        if idx not in all_pass_id:
            results=np.zeros(len(DEFAULT_PR))
            all_score.append(results)
            continue
        for constraint in DEFAULT_PR:
            vars_dict = deepcopy(func_dict)
            vars_dict["plan"] = plan

            try:
                execute_dsl_code(constraint, vars_dict, allowed_builtins={"set": set})
                res_i = vars_dict.get("result", False)
                results.append(clamp(res_i))
            except Exception as e:
                results.append(0.)
        all_score.append(np.array(results))
    if len(all_score)==0:
        return np.zeros(len(DEFAULT_PR))
    print(np.mean(all_score,axis=0))
    return np.mean(all_score,axis=0)



def load_result(args, query_index,path, verbose=False):
    def load_result_for_method(path):
        plans = {}
        for query_id in query_index:
            result_file = os.path.join(
                path, "{}.json".format(query_id)
            )

            try:
                if os.path.exists(result_file):
                    from chinatravel.evaluation.utils import load_json_file

                    result = load_json_file(result_file)
                    plans[query_id] = result
                else:
                    plans[query_id] = {}
            except:
                plans[query_id] = {}
        return plans

    result = {}

    result['default'] = load_result_for_method(path)

    if verbose:
        print(result)

    return ['default'], result

def write_file(file, content):
    """ Write content in file.
    """
    with open(file, 'a', encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--splits", "-s", type=str, default="example")
    parser.add_argument(
        "--method", "-m", type=str, default="travel_agent"
    )
    parser.add_argument("--preference", "-p", action="store_true", default=False)
    parser.add_argument("--lang", "--locale", choices=["zh", "en"], default="zh")
    args = parser.parse_args()
    from chinatravel.agent.load_model import ensure_method_language

    args.method = ensure_method_language(args.method, args.lang)

    # print(args.splits)

    from chinatravel.data.load_datasets import load_query
    from chinatravel.evaluation.commonsense_constraint import (
        evaluate_commonsense_constraints,
    )
    from chinatravel.evaluation.hard_constraint import evaluate_hard_constraints_v2
    from chinatravel.evaluation.preference import evaluate_preference_v2
    from chinatravel.evaluation.schema_constraint import evaluate_schema_constraints
    from chinatravel.evaluation.utils import load_json_file


    query_index, query_data = load_query(args)

    results_dir = os.path.join("results", args.method)
    method_list, result_data = load_result(args, query_index, results_dir)

    schema_file_path = 'chinatravel/evaluation/output_schema.json'
    schema = load_json_file(schema_file_path)


    scores = {}
    for method in method_list:




        print("Method: {}".format(args.method))

        if not os.path.exists("eval_res/splits_{}/{}/".format(args.splits, method)):
            os.makedirs("eval_res/splits_{}/{}/".format(args.splits, method))

        schema_rate, schema_result_agg, schema_pass_id = evaluate_schema_constraints(
            query_index, result_data[method], schema=schema
        )
        # print("Schema Pass Rate:", schema_rate)

        macro_comm, micro_comm, common_result_agg, commonsense_pass_id = evaluate_commonsense_constraints(
            query_index, query_data, result_data[method], verbose=False, lang=args.lang
        )

        # print("Commonsense constraints:")
        print("Mic.EPR {}".format(micro_comm))
        scores['MicEPR'] = micro_comm
        print("Mac.EPR: {}".format(macro_comm))
        scores['MacEPR'] = macro_comm

        # print("Logical constraints (python version):")
        macro_logi, micro_logi, conditional_macro_logi, conditional_micro_logi, logi_result_agg, logi_pass_id = evaluate_hard_constraints_v2(
            query_index, query_data, result_data[method], env_pass_id=commonsense_pass_id, verbose=False, lang=args.lang
        )




        print("C-LPR: {}".format(conditional_micro_logi))
        scores['C-LPR'] = conditional_micro_logi

        # record the index of the queries that pass the logical constraints
        logical_pass_info = logi_result_agg.iloc[:, 1:]
        id_list = logi_result_agg.iloc[:, 0].tolist()

        all_pass_id = list(set(schema_pass_id) & set(commonsense_pass_id) & set(logi_pass_id))


        print("FPR: ", 1. * len(all_pass_id) / len(query_index) * 100)
        fpr= 1. * len(all_pass_id) / len(query_index) * 100
        scores['FPR'] = fpr

        pre_res=cal_default_pr_score(query_index,query_data,result_data[method],all_pass_id)
        scores['DAV']=pre_res[0]*100
        scores['ATT']=pre_res[1]*100
        scores['DDR']=pre_res[2]*100

        final_score=0.1*micro_comm+0.1*macro_comm+0.25*conditional_micro_logi+0.05*scores['DAV']+0.05*scores['ATT']+0.05*scores['DDR']+0.4*fpr
        print('Overall Score: ',final_score)
        scores['overall'] = final_score
        print(scores)

        score_file = os.path.join('your_tpc_scores.json')
        write_file(score_file, json.dumps(scores))
        if args.preference:
            print("Preference:")
            result_agg = evaluate_preference_v2(
                query_index,
                query_data,
                result_data[method],
                list(set(commonsense_pass_id) & set(logi_pass_id)),
                lang=args.lang,
            )
