

import argparse
import ast

import numpy as np

import re
import os
import json

import time

from chinatravel.agent.utils import Logger, NpEncoder
from chinatravel.agent.nesy_agent.utils import time_compare_if_earlier_equal, add_time_delta
from chinatravel.agent.nesy_agent.prompts import (
    NEXT_POI_TYPE_INSTRUCTION,
    INTERCITY_TRANSPORT_GO_INSTRUCTION,
    INTERCITY_TRANSPORT_BACK_INSTRUCTION,
    HOTEL_RANKING_INSTRUCTION,
    ATTRACTION_RANKING_INSTRUCTION,
    RESTAURANT_RANKING_INSTRUCTION,
    SELECT_POI_TIME_INSTRUCTION,
    ROOMS_PLANNING_INSTRUCTION,
    BUDGETS_INSTRUCTION,
    INNERCITY_TRANSPORTS_SELECTION_INSTRUCTION,
)
from chinatravel.agent.nesy_agent.nesy_agent import NesyAgent

from chinatravel.data.load_datasets import load_query, load_json_file, save_json_file

class LLMDrivenAgent(NesyAgent):
    def __init__(self, **kwargs):
        kwargs["method"] = "LLMNeSy"
        super().__init__(**kwargs)
        if self.lang == "en":
            from chinatravel.agent.nesy_agent.prompts import prompts_en

            for prompt_name in [
                "NEXT_POI_TYPE_INSTRUCTION",
                "INTERCITY_TRANSPORT_GO_INSTRUCTION",
                "INTERCITY_TRANSPORT_BACK_INSTRUCTION",
                "HOTEL_RANKING_INSTRUCTION",
                "ATTRACTION_RANKING_INSTRUCTION",
                "RESTAURANT_RANKING_INSTRUCTION",
                "SELECT_POI_TIME_INSTRUCTION",
                "ROOMS_PLANNING_INSTRUCTION",
                "BUDGETS_INSTRUCTION",
                "INNERCITY_TRANSPORTS_SELECTION_INSTRUCTION",
            ]:
                globals()[prompt_name] = getattr(prompts_en, prompt_name)
        # self.ret=Retriever()
        self.ranking_attractions_flag= False
        self.ranking_restaurants_flag= False

    def ranking_intercity_transport_go(self, transport_info, query):

        time_before = time.time()

        query_message=[{"role": "user", "content": INTERCITY_TRANSPORT_GO_INSTRUCTION.format(user_requirements=query, transport_info=str(transport_info))}]
        answer = self.backbone_llm(query_message,one_line=False)

        self.llm_inference_time_count += time.time() - time_before

        self.llm_rec_count += 1

        print(answer)
        match = re.search(r'IDList:\s*(\[[^\]]+\])', answer)
        # if match:
        try:
            intercity_transport_list = ast.literal_eval(match.group(1))
            print('selected intercity_transports: ',intercity_transport_list)
            # print(intercity_transport_list)

            ranking_idx = []
            for cand_i in intercity_transport_list:
                if 'FL' in cand_i:
                    selected_index = transport_info['FlightID']==cand_i
                else:
                    selected_index = transport_info['TrainID']==cand_i
                if np.any(selected_index):
                    selected_index = np.where(selected_index)[0][0]
                    ranking_idx.append(selected_index)
        except Exception as e:
            print("!!!Error in eval intercity_transport_list", e)

            self.llm_rec_format_error += 1

        # else:
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


        time_before = time.time()
        query_message=[{"role": "user", "content": INTERCITY_TRANSPORT_BACK_INSTRUCTION.format(user_requirements=query, transport_info=str(transport_info), selected_go_info=str(selected_go))}]

        answer = self.backbone_llm(query_message,one_line=False)

        self.llm_inference_time_count += time.time() - time_before

        self.llm_rec_count += 1
        print(answer)
        match = re.search(r'IDList:\s*(\[[^\]]+\])', answer)
        # if match:
        try:
            intercity_transport_list = ast.literal_eval(match.group(1))
            print('selected intercity_transports: ',intercity_transport_list)

            # print(intercity_transport_list)

            ranking_idx = []
            for cand_i in intercity_transport_list:
                if 'FL' in cand_i:
                    selected_index = transport_info['FlightID']==cand_i
                else:
                    selected_index = transport_info['TrainID']==cand_i

                if np.any(selected_index):
                    selected_index = np.where(selected_index)[0][0]
                    ranking_idx.append(selected_index)
        except Exception as e:
            print("!!!Error in eval intercity_transport_list", e)
            self.llm_rec_format_error += 1

        # else:
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

    def ranking_hotel(self, hotel_info, query):

        print(hotel_info.head())

        hotel_info = hotel_info.drop(columns=["hotelname_en"])

        time_before = time.time()
        # filtering hotel info by llm
        query_message=[{"role": "user", "content": HOTEL_RANKING_INSTRUCTION.format(user_requirements=query, hotel_info=str(hotel_info))}]
        answer = self.backbone_llm(query_message,one_line=False)


        self.llm_inference_time_count += time.time() - time_before
        self.llm_rec_count += 1

        print(answer)
        match = re.search(r'HotelNameList:\s*\[(.*?)\]', answer, re.DOTALL)

        ranking_idx = []
        # if match:
        try:
            HotelNameList = re.findall(r'"([^"]+)"', match.group(1))

            print('selected HotelNameList: ',HotelNameList)
            for cand_i in HotelNameList:
                selected_index = np.where(hotel_info['name']==cand_i)[0][0]
                ranking_idx.append(selected_index)
        except:
            print("!!!Error in eval HotelNameList")
            self.llm_rec_format_error += 1

            cost_list = hotel_info["price"].tolist()
            sorted_lst = sorted(zip(range(len(hotel_info["price"])), cost_list), key=lambda x: x[1])
            sorted_indices = [index for index, value in sorted_lst]
            for r_i in sorted_indices:
                if r_i not in ranking_idx:
                    ranking_idx.append(r_i)

        return ranking_idx




    def select_and_add_breakfast(self, plan, poi_plan, current_day, current_time, current_position):

        # have breakfast at hotel
        plan[current_day]["activities"] = self.add_poi(plan[current_day]["activities"], poi_plan["accommodation"]["name"], "breakfast", 0, 0, "08:00", "08:30", innercity_transports=[])
        return plan

    def select_next_poi_type(self, candidates_type, plan, poi_plan, current_day, current_time, current_position):

        if current_day == self.query["days"]-1:
            if time_compare_if_earlier_equal(poi_plan["back_transport"]["BeginTime"], add_time_delta(current_time, 180)):
                return "back-intercity-transport", ["back-intercity-transport"]

        time_before = time.time()
        query_message=[{"role": "user", "content": NEXT_POI_TYPE_INSTRUCTION.format(self.query['nature_language'], poi_plan,current_day+1, current_time, current_position,candidates_type)}]
        answer=self.backbone_llm(query_message,one_line=False)

        self.llm_rec_count += 1


        self.llm_inference_time_count += time.time() - time_before

        poi_type=None
        match = re.search(r'Type:\s*(\w+)', answer)
        if match:
            poi_type = match.group(1)
        else:
            self.llm_rec_format_error += 1

        if poi_type is not None and poi_type in candidates_type:
            return poi_type, candidates_type
        else:
            print("The selected POI type is not in the candidate POI type list.")
            return candidates_type[0], candidates_type



    def ranking_attractions(self, plan, poi_plan, current_day, current_time, current_position, intercity_with_hotel_cost):

        if self.ranking_attractions_flag:
            pass
        else:

            # print(self.memory["attractions"])

            attr_info = self.memory["attractions"][["name","type","opentime","endtime","price"]]

            time_before = time.time()
            query_message=[{"role": "user", "content": ATTRACTION_RANKING_INSTRUCTION.format(user_requirements=self.query['nature_language'], attraction_info=str(attr_info), past_cost=intercity_with_hotel_cost)}]
            answer=self.backbone_llm(query_message,one_line=False)


            self.llm_inference_time_count += time.time() - time_before

            attraction_list=[]
            match = re.search(r'AttractionNameList:\s*(\[[^\]]+\])', answer)
            if match:
                try:
                    attraction_list = ast.literal_eval(match.group(1))
                except:
                    print("!!!Error in eval attraction_list")
            print('selected attractions: ',attraction_list)
            self.suggested_attractions_from_query = attraction_list
            self.ranking_attractions_flag = True

        attraction_list = self.suggested_attractions_from_query
        num_attractions = len(self.memory["attractions"])
        attr_info = self.memory["attractions"]

        attr_price = attr_info["price"].values

        ranking_price = np.argsort(np.array(attr_price))

        attr_dist = []
        for i in range(num_attractions):
            if current_position == attr_info.iloc[i]["name"]:
                attr_dist.append(0)
            else:
                transports_sel = self.collect_innercity_transport(self.query["target_city"], current_position, attr_info.iloc[i]["name"], current_time, "walk")
                attr_dist.append(transports_sel[0]["distance"])


        ranking_dist = np.argsort(np.array(attr_dist))

        if len(attraction_list) > 0:
            for id, selected_i in enumerate(attraction_list):
                attr_i = attr_info[attr_info["name"] == selected_i].index
                ranking_price[attr_i] = -len(attraction_list) + id
                ranking_dist[attr_i] = -len(attraction_list) + id


        ranking_idx = np.argsort(ranking_price + ranking_dist)

        return ranking_idx

    def ranking_restaurants(self, plan, poi_plan, current_day, current_time, current_position, intercity_with_hotel_cost):

        if self.ranking_restaurants_flag:
            pass
        else:
            res_info=self.memory["restaurants"][["name","cuisine","price","opentime","endtime","recommendedfood"]]


            time_before = time.time()
            query_message=[{"role": "user", "content": RESTAURANT_RANKING_INSTRUCTION.format(user_requirements=self.query['nature_language'], restaurant_info=str(res_info), past_cost=intercity_with_hotel_cost, days=self.query['days'])}]
            answer=self.backbone_llm(query_message,one_line=False)


            self.llm_inference_time_count += time.time() - time_before

            print(answer)
            restaurant_list=[]
            match = re.search(r'RestaurantNameList:\s*(\[[^\]]+\])', answer)
            if match:
                try:
                    restaurant_list = ast.literal_eval(match.group(1))
                except:
                    print("!!!Error in eval restaurant_list")
            print('selected restaurants: ',restaurant_list)
            self.suggested_restaurants_from_query = restaurant_list
            self.ranking_restaurants_flag = True

        restaurant_list = self.suggested_restaurants_from_query
        num_restaurants = len(self.memory["restaurants"])
        res_info = self.memory["restaurants"]

        res_price = res_info["price"].values

        ranking_price = np.argsort(np.array(res_price))

        attr_dist = []
        for i in range(num_restaurants):

            if current_position == res_info.iloc[i]["name"]:
                attr_dist.append(0)
            else:
                transports_sel = self.collect_innercity_transport(self.query["target_city"], current_position, res_info.iloc[i]["name"], current_time, "walk")
                attr_dist.append(transports_sel[0]["distance"])


        ranking_dist = np.argsort(np.array(attr_dist))

        if len(restaurant_list) > 0:
            for id, selected_i in enumerate(restaurant_list):
                res_i = res_info[res_info["name"] == selected_i].index
                ranking_price[res_i] = -len(restaurant_list) + id
                ranking_dist[res_i] = -len(restaurant_list) + id


        ranking_idx = np.argsort(ranking_price + ranking_dist)


        return ranking_idx

    def select_poi_time(self, plan, poi_plan, current_day, start_time, poi_name, poi_type, recommended_visit_time):

        return 90
        time_before = time.time()

        query_message=[{"role": "user", "content": SELECT_POI_TIME_INSTRUCTION.format(user_requirements=self.query['nature_language'], current_travel_plans=poi_plan,
                                                                                      current_date=current_day+1, current_time=start_time,
                                                                                      current_poi=poi_name, poi_type=poi_type, recommended_visit_time=recommended_visit_time,
                                                                                      back_transport_time=poi_plan["back_transport"]["BeginTime"])}]
        answer=self.backbone_llm(query_message,one_line=False)


        self.llm_inference_time_count += time.time() - time_before

        poi_time=None
        match = re.search(r'Time:\s*(\w+)', answer)
        if match:
            poi_time = match.group(1)
        try:
            poi_time = int(poi_time)
        except:
            poi_time = 90
        return poi_time

    def decide_rooms(self, query):

        time_before = time.time()

        query_message=[{"role": "user", "content": ROOMS_PLANNING_INSTRUCTION.format(user_requirements=self.query['nature_language'])}]
        answer=self.backbone_llm(query_message,one_line=False)


        self.llm_inference_time_count += time.time() - time_before

        self.llm_rec_count += 1

        room_info_pattern = re.compile(r'RoomInfo:\s*\[\s*(\d+|\-1)\s*,\s*(\d+|\-1)\s*\]')

        match = room_info_pattern.search(answer)

        if match:
            num_rooms = int(match.group(1))
            num_beds = int(match.group(2))
            if num_rooms < 1:
                num_rooms = None
            if num_beds < 1:
                num_beds = None
        else:
            print("!!!Error in matching RoomInfo")
            num_rooms, num_beds = None, None

            self.llm_rec_format_error += 1


        # print(answer)
        print("extracted room_number: ", num_rooms, "room_type:", num_beds)
        return num_rooms, num_beds
    def extract_budget(self, query):

        time_before = time.time()

        query_message=[{"role": "user", "content": BUDGETS_INSTRUCTION.format(user_requirements=self.query['nature_language'])}]
        answer=self.backbone_llm(query_message,one_line=False)


        self.llm_inference_time_count += time.time() - time_before

        self.llm_rec_count += 1

        budget_pattern = r"Budget: (\d+)"

        match = re.search(budget_pattern, answer)

        if match:
            budget = int(match.group(1))
            if budget < 1:
                budget = None
        else:
            print("!!!Error in extracting budget")
            budget = None

            self.llm_rec_format_error += 1


        # print(answer)
        print("extracted budget: ", budget)
        # exit(0)
        return budget

    def ranking_innercity_transport_from_query(self, query):

        time_before = time.time()

        query_message=[{"role": "user", "content": INNERCITY_TRANSPORTS_SELECTION_INSTRUCTION.format(user_requirements=query['nature_language'])}]
        answer=self.backbone_llm(query_message,one_line=False)

        print(answer)

        self.llm_inference_time_count += time.time() - time_before

        self.llm_rec_count += 1

        match = re.search(r'TransportRanking:\s*\[(.*?)\]', answer, re.DOTALL)
        if match:
            try:
                TransportRanking = re.findall(r'"([^"]+)"', match.group(1))
            except:
                print("!!!Error in eval TransportRanking")
                self.llm_rec_format_error += 1
                TransportRanking = []

            print('selected TransportRanking: ',TransportRanking)
            rank_ = []
            for item in TransportRanking:
                if item in ["metro", "taxi", "walk"]:
                    rank_.append(item)
            if len(rank_):
                TransportRanking = rank_
            else:
                TransportRanking = ["metro", "taxi", "walk"]
        else:
            TransportRanking = ["metro", "taxi", "walk"]
        if (len(TransportRanking) == 0):
            TransportRanking = ["metro", "taxi", "walk"]
        return TransportRanking

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='argparse testing')
    parser.add_argument('--splits','-l',type=str, default = "easy",choices=["easy", "medium", "human"], help="query subset")
    parser.add_argument('--index','-i',type=str, default = None, help="query index")
    parser.add_argument('--skip-exist','-sk',type=int, default =0, help="skip if the plan exists")
    parser.add_argument('--llm','-m',type=str, default=None)
    parser.add_argument('--oracle_translation', action='store_true', help='Set this flag to enable oracle translation.')

    args = parser.parse_args()

    # from eval.test import load_query
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

    method = build_method_name(
        "LLMNeSy",
        args.llm,
        oracle_translation=args.oracle_translation,
    )

    cache_dir = os.path.join(project_root_path, "cache")

    agent = LLMDrivenAgent(env=env, backbone_llm=llm, cache_dir=cache_dir, search_width=30, debug=True)

    res_dir = os.path.join(project_root_path, "results", method)
    if not os.path.exists(res_dir):
        os.makedirs(res_dir)

    print(res_dir)

    white_list = []

    succ_count = 0
    for i, data_idx in enumerate(query_index):

        print("Process [{}/{}], Success [{}/{}]: \n--------------------\n".format(i, len(query_index), succ_count, len(query_index)))
        if args.skip_exist and os.path.exists(os.path.join(res_dir, f"{data_idx}.json")):
            continue
        if i in white_list:
            continue
        symbolic_input = query_data[data_idx]
        print(symbolic_input)


        succ, plan = agent.run(symbolic_input, load_cache=True, oralce_translation=args.oracle_translation)
        # print(plan)
        # print(succ)
        # exit(0)
        if succ:
            succ_count += 1
        save_json_file(json_data=plan, file_path=os.path.join(res_dir, f"{data_idx}.json"))
