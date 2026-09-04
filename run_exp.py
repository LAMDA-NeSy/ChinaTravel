import argparse

import sys
import os
import json

project_root_path = os.path.dirname(os.path.abspath(__file__))


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="argparse testing")
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
        required=True,
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
    parser.add_argument("--lang", "--locale", choices=["zh", "en"], default="zh", help="Language environment to load.")


    args = parser.parse_args()
    from chinatravel.agent.load_model import (
        create_agent_runtime,
        resolve_agent_llm_name,
    )

    args.llm = resolve_agent_llm_name(args.agent, args.llm)
    if not args.llm:
        parser.error(
            "No model configured. Pass --llm <model> or set CHINATRAVEL_OPENAI_MODEL/OPENAI_MODEL."
        )

    print(args)

    from chinatravel.data.load_datasets import load_query, save_json_file

    query_index, query_data = load_query(args)
    print(len(query_index), "samples")

    if args.index is not None:
        query_index = [args.index]

    if args.agent == "LLM-modulo":
        if not args.oracle_translation:
            raise Exception("LLM-modulo must use oracle translation")

    runtime = create_agent_runtime(
        args.agent,
        args.llm,
        project_root_path=project_root_path,
        lang=args.lang,
        oracle_translation=args.oracle_translation,
        preference_search=args.preference_search,
        refine_steps=args.refine_steps,
    )
    res_dir = runtime.result_dir
    log_dir = runtime.log_dir
    agent = runtime.agent

    print("res_dir: ", res_dir)
    print("log_dir:", log_dir)


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
            plan_log = agent(query_i["nature_language"])
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
