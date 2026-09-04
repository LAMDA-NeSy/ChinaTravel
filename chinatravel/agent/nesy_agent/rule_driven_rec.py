import argparse

import numpy as np

import os
import json


# from chinatravel.agent.utils import Logger, NpEncoder, load_json_file, save_json_file
from chinatravel.agent.nesy_agent.nesy_agent import NesyAgent
from chinatravel.agent.nesy_agent.utils import (
    time_compare_if_earlier_equal,
    add_time_delta,
)
from chinatravel.data.load_datasets import load_query, load_json_file, save_json_file
from chinatravel.symbol_verification.hard_constraint import (
    get_symbolic_concepts,
    evaluate_constraints,
    evaluate_constraints_py,
)

class RuleDrivenAgent(NesyAgent):
    def __init__(self, **kwargs):
        kwargs["method"] = "RuleNeSy"
        super().__init__(**kwargs)

    def ranking_intercity_transport_go(self, transport_info, query):
        time_list = transport_info["BeginTime"].tolist()
        sorted_lst = sorted(enumerate(time_list), key=lambda x: x[1])
        sorted_indices = [index for index, value in sorted_lst]
        time_ranking = np.zeros_like(sorted_indices)
        for i, idx in enumerate(sorted_indices):
            time_ranking[idx] = i + 1

        price_list = transport_info["Cost"].tolist()
        price_ranking = np.argsort(np.array(price_list))

        ranking_idx = np.argsort(time_ranking + price_ranking)

        return ranking_idx

    def ranking_intercity_transport_back(self, transport_info, query, selected_go):
        time_list = transport_info["BeginTime"].tolist()
        sorted_lst = sorted(enumerate(time_list), key=lambda x: x[1])
        sorted_indices = [index for index, value in sorted_lst]
        sorted_indices.reverse()
        time_ranking = np.zeros_like(sorted_indices)
        for i, idx in enumerate(sorted_indices):
            time_ranking[idx] = i + 1

        price_list = transport_info["Cost"].tolist()
        price_ranking = np.argsort(np.array(price_list))

        ranking_idx = np.argsort(time_ranking + price_ranking)

        return ranking_idx
        return sorted_indices

    def ranking_hotel(self, hotel_info, query):

        # ranking by cost

        print(hotel_info.head())

        num_hotel = hotel_info.shape[0]

        # print("{} accommmodation, {} hotels (satisfied requirments)".format(query["target_city"], num_hotel))

        index_list = hotel_info["id"].tolist()

        # if "cost" in query:
        cost_list = hotel_info["price"].tolist()
        sorted_lst = sorted(zip(index_list, cost_list), key=lambda x: x[1])
        sorted_indices = [index for index, value in sorted_lst]
        # print(sorted_indices)
        # for idx in sorted_indices:
        #     print(hotel_info.iloc[idx]["price"])
        index_list = sorted_indices



        return index_list
    
    def check_if_too_late(
        self, query, current_day, current_time, current_position, poi_plan
    ):

        if current_time != "" and time_compare_if_earlier_equal("23:00", current_time):
            print("too late, after 23:00")
            return True

        if current_time != "" and current_day == query["days"] - 1:
            # We should go back in time ...
            transports_ranking = self.ranking_innercity_transport(
                current_position,
                poi_plan["back_transport"]["From"],
                current_day,
                current_time,
            )

            for transport_type_sel in transports_ranking:

                flag = True
                if "back_transport" in poi_plan:
                    transports_sel = self.collect_innercity_transport(
                        query["target_city"],
                        current_position,
                        poi_plan["back_transport"]["From"],
                        current_time,
                        transport_type_sel,
                    )
                    if not isinstance(transports_sel, list):
                            continue
                    if len(transports_sel) == 0:
                        arrived_time = current_time
                    else:
                        arrived_time = transports_sel[-1]["end_time"]

                    if not time_compare_if_earlier_equal(
                        poi_plan["back_transport"]["BeginTime"], arrived_time
                    ):
                        flag = False
                if flag:
                    print(
                        "Can not go back source-city in time, current POI {}, station arrived time: {}".format(
                            current_position, arrived_time
                        )
                    )
                    return True

        elif current_time != "":
            if "accommodation" in poi_plan:
                hotel_sel = poi_plan["accommodation"]
                transports_ranking = self.ranking_innercity_transport(
                    current_position, hotel_sel["name"], current_day, current_time
                )

                for transport_type_sel in transports_ranking:

                    flag = True
                    if "back_transport" in poi_plan:
                        transports_sel = self.collect_innercity_transport(
                            query["target_city"],
                            current_position,
                            hotel_sel["name"],
                            current_time,
                            transport_type_sel,
                        )

                        flag = True
                        if not isinstance(transports_sel, list):
                            continue
                        if len(transports_sel) == 0:
                            arrived_time = current_time
                        else:
                            arrived_time = transports_sel[-1]["end_time"]
                        if not time_compare_if_earlier_equal("24:00", arrived_time):
                            flag = False
                    if flag:
                        print(
                            "Can not go back to hotel, current POI {}, hotel arrived time: {}".format(
                                current_position, arrived_time
                            )
                        )
                        return True

        return False

    def select_and_add_breakfast(
        self, plan, poi_plan, current_day, current_time, current_position
    ):

        # have breakfast at hotel
        plan[current_day]["activities"] = self.add_poi(
            plan[current_day]["activities"],
            poi_plan["accommodation"]["name"],
            "breakfast",
            0,
            0,
            "08:00",
            "08:30",
            innercity_transports=[],
        )
        return plan

    def select_next_poi_type(
        self,
        candidates_type,
        plan,
        poi_plan,
        current_day,
        current_time,
        current_position,
    ):

        if current_day == self.query["days"] - 1:
            if time_compare_if_earlier_equal(
                poi_plan["back_transport"]["BeginTime"],
                add_time_delta(current_time, 180),
            ):
                return "back-intercity-transport", ["back-intercity-transport"]

        haved_lunch_today, haved_dinner_today = False, False
        candidates_type = ["attraction"]
        if (not haved_lunch_today) and time_compare_if_earlier_equal(
            current_time, "12:30"
        ):
            candidates_type.append("lunch")
        if (not haved_dinner_today) and time_compare_if_earlier_equal(
            current_time, "18:30"
        ):
            candidates_type.append("dinner")
        if "accommodation" in poi_plan and current_day < self.query["days"] - 1:
            candidates_type.append("hotel")

        hour, minuate = int(current_time.split(":")[0]), int(current_time.split(":")[1])

        # too late
        if (
            time_compare_if_earlier_equal("22:30", add_time_delta(current_time, 120))
            and "hotel" in candidates_type
        ):
            return "hotel", ["hotel"]

        # lunch time
        if ("lunch" in candidates_type) and (
            time_compare_if_earlier_equal("11:00", add_time_delta(current_time, 40))
            or time_compare_if_earlier_equal("12:40", add_time_delta(current_time, 120))
        ):
            return "lunch", ["lunch"]

        # dinner time
        if ("dinner" in candidates_type) and (
            time_compare_if_earlier_equal("17:00", add_time_delta(current_time, 40))
            or time_compare_if_earlier_equal("19:00", add_time_delta(current_time, 120))
        ):
            return "dinner", ["dinner"]

        return "attraction", candidates_type
        return "attraction", ["attraction"]

    def ranking_attractions(
        self,
        plan,
        poi_plan,
        current_day,
        current_time,
        current_position,
        intercity_with_hotel_cost,
    ):

        # ranking by distance
        num_attractions = len(self.memory["attractions"])
        attr_weight = np.ones(num_attractions)
        attr_info = self.memory["attractions"]

        attr_dist = []
        for i in range(num_attractions):
            transports_sel = self.collect_innercity_transport(
                self.query["target_city"],
                current_position,
                attr_info.iloc[i]["name"],
                current_time,
                "walk",
            )
            if len(transports_sel) == 0:
                attr_dist.append(0)
            else:
                attr_dist.append(transports_sel[0]["distance"])
        # print(attr_dist)

        ranking_idx = np.argsort(np.array(attr_dist))

        attr_price = attr_info["price"].values

        ranking_price = np.argsort(np.array(attr_price))

        ranking_dist = np.argsort(np.array(attr_dist))

        ranking_idx = np.argsort(ranking_price + ranking_dist)

        return ranking_idx

    def ranking_restaurants(
        self,
        plan,
        poi_plan,
        current_day,
        current_time,
        current_position,
        intercity_with_hotel_cost,
    ):

        # ranking by cost and distance
        num_restaurants = len(self.memory["restaurants"])
        res_weight = np.ones(num_restaurants)
        res_info = self.memory["restaurants"]

        res_price = res_info["price"].values

        ranking_price = np.argsort(np.array(res_price))

        attr_dist = []
        for i in range(num_restaurants):
            transports_sel = self.collect_innercity_transport(
                self.query["target_city"],
                current_position,
                res_info.iloc[i]["name"],
                current_time,
                "walk",
            )
            if len(transports_sel) == 0:
                attr_dist.append(0)
            else:            
                attr_dist.append(transports_sel[0]["distance"])

        ranking_dist = np.argsort(np.array(attr_dist))

        ranking_idx = np.argsort(ranking_price + ranking_dist)
        return ranking_idx

    def ranking_innercity_transport(
        self, current_position, target_position, current_day, current_time
    ):

        return ["metro", "taxi", "walk"]

    def ranking_innercity_transport_from_query(self, query):

        return ["metro", "taxi", "walk"]

    def select_poi_time(
        self,
        plan,
        poi_plan,
        current_day,
        start_time,
        poi_name,
        poi_type,
        recommended_visit_time,
    ):
        return 90

    def decide_rooms(self, query):
        return None, None
    def extract_budget(self, query):
        return None

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="argparse testing")
    parser.add_argument(
        "--splits",
        "-l",
        type=str,
        default="easy",
        choices=["easy", "easy_day1", "medium", "human"],
        help="query subset",
    )
    parser.add_argument("--index", "-i", type=str, default=None, help="query index")
    parser.add_argument(
        "--skip-exist", "-sk", type=int, default=0, help="skip if the plan exists"
    )
    parser.add_argument("--llm", "-m", type=str, default="rule")
    parser.add_argument(
        "--oracle_translation",
        action="store_true",
        help="Set this flag to enable oracle translation.",
    )
    args = parser.parse_args()

    from chinatravel.data.load_datasets import load_query
    from chinatravel.agent.llms import create_llm
    from chinatravel.agent.load_model import build_method_name
    from chinatravel.environment.world_env import WorldEnv

    env = WorldEnv()

    query_index, query_data = load_query(args)

    # print(query_index, query_data)
    print(len(query_index), "samples")

    if args.index is not None:
        query_index = [args.index]

    llm = create_llm(args.llm)

    method = build_method_name("RuleNeSy", args.llm)

    os.environ["OPENAI_API_KEY"] = ""

    cache_dir = os.path.join(project_root_path, "cache")

    agent = RuleDrivenAgent(
        env=env, backbone_llm=llm, cache_dir=cache_dir, search_width=30, debug=True
    )

    res_dir = os.path.join(project_root_path, "results", method)
    if not os.path.exists(res_dir):
        os.makedirs(res_dir)

    print(res_dir)

    white_list = []

    succ_count, eval_count = 0, 0

    for i, data_idx in enumerate(query_index):

        print(
            "Process [{}/{}], Success [{}/{}]: \n--------------------\n".format(
                i, len(query_index), succ_count, eval_count
            )
        )

        if args.skip_exist and os.path.exists(
            os.path.join(res_dir, f"{data_idx}.json")
        ):
            continue
        if i in white_list:
            continue

        eval_count += 1

        symbolic_input = query_data[data_idx]
        print(symbolic_input)

        # exit(0)

        # succ, plan = agent.run(symbolic_input, load_cache=True, oralce_translation=True)
        succ, plan = agent.run(symbolic_input, load_cache=True)

        if succ:
            succ_count += 1

        save_json_file(
            json_data=plan, file_path=os.path.join(res_dir, f"{data_idx}.json")
        )
