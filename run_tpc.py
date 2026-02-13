import argparse

import numpy as np

import sys
import os
import json
from func_timeout import func_timeout, FunctionTimedOut

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
        default="tpc_phase1",
        help="query subset",
    )
    parser.add_argument("--index", "-id", type=str, default=None, help="query index")
    parser.add_argument(
        "--skip", "-sk", type=int, default=0, help="skip if the plan exists"
    )
    parser.add_argument(
        "--agent",
        "-a",
        type=str,
        default=None,
        choices=["TPCAgent"],
    )
    parser.add_argument(
        "--llm",
        "-l",
        type=str,
        default=None
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=300,
        help="Timeout in seconds for each query",
    )

    parser.add_argument('--oracle_translation', action='store_true', help='Set this flag to enable oracle translation.')

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

    kwargs = {
        "method": args.agent,
        "env": WorldEnv(en_version=args.lang == "en"),
        "backbone_llm": init_llm(args.llm),
        "cache_dir": cache_dir,
        "log_dir": log_dir, 
        "debug": True,
    }
    agent = init_agent(kwargs)

    succ_count, eval_count = 0, 0

    for i, data_idx in enumerate(query_index):

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
        eval_count += 1
        query_i = query_data[data_idx]
        print(query_i)
        try:
            # succ, plan = agent.run(query_i, prob_idx=data_idx, oralce_translation=args.oracle_translation)
            succ, plan = func_timeout(
                args.timeout,
                agent.run,
                args=(query_i,),
                kwargs=dict(
                    prob_idx=data_idx, oralce_translation=args.oracle_translation
                ),
            )
        except FunctionTimedOut:
            # print(f"⚠️ 任务 {data_idx} 超过 {args.timeout}s 被中断。")
            succ, plan = 0, {"error": f"timeout after {args.timeout}s"}

        except Exception as e:
            # print(f"❌ 执行任务 {data_idx} 出错: {e}")
            succ, plan = 0, {"error": str(e)}

        if succ:
            succ_count += 1

        save_json_file(
            json_data=plan, file_path=os.path.join(res_dir, f"{data_idx}.json")
        )
