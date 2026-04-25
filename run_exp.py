import argparse

import numpy as np

import sys
import os
import json

project_root_path = os.path.dirname(os.path.abspath(__file__))
if project_root_path not in sys.path:
    sys.path.insert(0, project_root_path)

from copy import deepcopy

from chinatravel.data.load_datasets import load_query, save_json_file
from chinatravel.agent.load_model import init_agent, init_llm
from chinatravel.environment.world_env import WorldEnv


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="argparse testing")
    parser.add_argument("--lang", type=str, default="zh", choices=["zh", "en"], help="dataset/environment language")
    parser.add_argument(
        "--splits",
        "-s",
        type=str,
        default="easy",
        help="query subset",
    )
    parser.add_argument("--index", "-id", type=str, default=None, help="query index")
    parser.add_argument(
        "--skip", "-sk", type=int, default=0, help="skip if the plan exists"
    )
    parser.add_argument('--restart_from', type=str, default=None, help='Restart Data ID')
    parser.add_argument(
        "--agent",
        "-a",
        type=str,
        default=None,
        choices=["RuleNeSy", "LLMNeSy", "LLM-modulo", "ReAct", "ReAct0", "Act", "TPCAgent"],
    )
    parser.add_argument(
        "--llm",
        "-l",
        type=str,
        default=None
    )
    
    parser.add_argument('--oracle_translation', action='store_true', help='Set this flag to enable oracle translation.')
    parser.add_argument('--preference_search', action='store_true', help='Set this flag to enable preference search.')
    parser.add_argument('--refine_steps', type=int, default=10, help='Steps for refine-based method, such as LLM-modulo, Reflection')
    

    args = parser.parse_args()

    print(args)

    query_index, query_data = load_query(args)
    print(len(query_index), "samples")

    if args.index is not None:
        query_index = [args.index]

    cache_dir = os.path.join(project_root_path, "cache")

    method = args.agent + "_" + args.llm
    if args.agent == "LLM-modulo":
        method += f"_{args.refine_steps}steps"

        if not args.oracle_translation:
            raise Exception("LLM-modulo must use oracle translation")

    if args.oracle_translation:
        method = method + "_oracletranslation"
    if args.preference_search:
        method = method + "_preferencesearch"

    res_dir = os.path.join(
        project_root_path, "results", method
    )
    log_dir = os.path.join(
        project_root_path, "cache", method
    )
    if not os.path.exists(res_dir):
        os.makedirs(res_dir)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    print("res_dir: ", res_dir)
    print("log_dir:", log_dir)

    if args.agent in ["LLM-modulo"]:
        max_model_len = 65536
    elif args.agent in ["LLMNeSy"]:
        max_model_len = 8192
    else:
        max_model_len = None
    kwargs = {
        "method": args.agent,
        "env": WorldEnv(en_version=args.lang == "en"),
        "backbone_llm": init_llm(args.llm, max_model_len=max_model_len),
        "cache_dir": cache_dir,
        "log_dir": log_dir, 
        "debug": True,
        "refine_steps": args.refine_steps,
    }
    agent = init_agent(kwargs)


    white_list = []

    succ_count, eval_count = 0, 0

    for i, data_idx in enumerate(query_index):
        if (args.restart_from is not None) and (data_idx != args.restart_from):
            continue
        else:
            args.restart_from = None

        sys.stdout = sys.__stdout__
        print("------------------------------")
        print(
            "Process [{}/{}], Success [{}/{}]:".format(
                i, len(query_index), succ_count, eval_count
            )
        )
        print("data uid: ", data_idx)

        if args.skip and os.path.exists(os.path.join(res_dir, f"{data_idx}.json")):
            continue
        if i in white_list:
            continue
        eval_count += 1
        query_i = query_data[data_idx]
        print(query_i)
        if args.agent in ["ReAct", "ReAct0", "Act"]:
            plan_log = agent(query_i.get("nature_language", query_i.get("nature_language_en", "")))
            plan = plan_log["ans"]
            if isinstance(plan, str):
                try:
                    plan = json.loads(plan)
                except:
                    plan = {"plan": plan}
            plan["input_token_count"] = agent.backbone_llm.input_token_count
            plan["output_token_count"] = agent.backbone_llm.output_token_count
            plan["input_token_maxx"] = agent.backbone_llm.input_token_maxx
            log = plan_log["log"]
            save_json_file(
                json_data=log, file_path=os.path.join(log_dir, f"{data_idx}.json")
            )
            succ = 1
        elif args.agent in ["LLM-modulo"]:
            
            succ, plan = agent.solve(query_i, prob_idx=data_idx, oracle_verifier=True)

        elif args.agent in ["LLMNeSy", "RuleNeSy"]:
            succ, plan = agent.run(query_i, load_cache=True, oralce_translation=args.oracle_translation, preference_search=args.preference_search)
        
        elif args.agent == "TPCAgent":
            succ, plan = agent.run(query_i, prob_idx=data_idx, oralce_translation=args.oracle_translation)

        if succ:
            succ_count += 1

        save_json_file(
            json_data=plan, file_path=os.path.join(res_dir, f"{data_idx}.json")
        )
