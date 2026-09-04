
import os

from chinatravel.agent.base import BaseAgent

from chinatravel.agent.nesy_verifier.prompts.llm_modulo import INITIAL_PROMPT, BACK_PROMPT
from chinatravel.agent.nesy_verifier.prompts.poi_selection import HOTEL_SELECTION_INSTRUCTION, ATTRACTION_SELECTION_INSTRUCTION, RESTAURANT_SELECTION_INSTRUCTION, TRANSPORT_GO_SELECTION_INSTRUCTION, TRANSPORT_BACK_SELECTION_INSTRUCTION
# from symbol_verification.commonsense_constraint import func_commonsense_constraints
from chinatravel.agent.nesy_verifier.verifier.commonsense_constraint_nl import collect_commonsense_constraints_error
from chinatravel.agent.nesy_verifier.verifier.personal_constraint_nl import collect_personal_error

import pandas as pd
import ast

from chinatravel.agent.utils import Logger

import numpy as np
import re
import json
from chinatravel.json_utils import repair_json
import time
from tqdm import tqdm

def calc_time_delta(st_time, ed_time):
    st_h, st_m = int(st_time.split(":")[0]), int(st_time.split(":")[1])
    ed_h, ed_m = int(ed_time.split(":")[0]), int(ed_time.split(":")[1])
    return (ed_m - st_m) + (ed_h - st_h) * 60

class LLMModuloAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="LLM-Modulo", **kwargs)

        self.env = kwargs.get('env', None)
        self.max_steps = kwargs.get('max_steps', 0)
        self.log_dir = os.path.join(self.log_dir, f'llm_modulo-{self.model_name}')
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        
        self.num_candidates_intercity_transports = 5 # 10
        self.num_candidates_accommodations = 3 # 10
        self.num_candidates_attractions = 15 # 50
        self.num_candidates_restaurants = 5 # 30

    def collect_poi_info_all(self, city, poi_type):

        if poi_type == "accommodation":
            func_name = "accommodations_select"
        elif poi_type == "attraction":
            func_name = "attractions_select"
        elif poi_type == "restaurant":
            func_name = "restaurants_select"
        else:
            raise NotImplementedError

        poi_info = self.env(
            "{func}('{city}', 'name', lambda x: True)".format(func=func_name, city=city)
        )["data"]
        # print(poi_info)
        while True:
            info_i = self.env("next_page()")["data"]
            if len(info_i) == 0:
                break
            else:
                poi_info = pd.concat([poi_info, info_i], axis=0, ignore_index=True)

        poi_info = poi_info.rename(columns={'cost': 'price'})
        return poi_info

    def collect_intercity_transport(self, source_city, target_city, trans_type):
        trans_info = self.env(
            "intercity_transport_select('{source_city}', '{target_city}', '{trans_type}')".format(
                source_city=source_city, target_city=target_city, trans_type=trans_type
            )
        )["data"]
        # print(poi_info)
        while True:
            info_i = self.env("next_page()")["data"]
            if len(info_i) == 0:
                break
            else:
                trans_info = pd.concat([trans_info, info_i], axis=0, ignore_index=True)
        # print(poi_info)
        trans_info = trans_info.rename(columns={'Cost': 'price'})
        return trans_info
    
    def collect_innercity_transport(self, city, start, end, start_time, trans_type):

        call_str = (
            'goto("{city}", "{start}", "{end}", "{start_time}", "{trans_type}")'.format(
                city=city,
                start=start,
                end=end,
                start_time=start_time,
                trans_type=trans_type,
            )
        )

        # print(call_str)
        if start == end:
            return []
        info = self.env(call_str)["data"]

        # print(start, end, info)

        if info == "No solution":
            return info

        if not isinstance(info, list):
            return "No solution"
        
        if len(info) == 3:
            info[1]["price"] = info[1]["cost"]
            info[1]["tickets"] = self.problem["people_number"]
            info[1]["cost"] = info[1]["price"] * info[1]["tickets"]

            info[0]["price"] = info[0]["cost"]
            info[2]["price"] = info[2]["cost"]
        elif info[0]["mode"] == "taxi":
            info[0]["price"] = info[0]["cost"]
            info[0]["cars"] = int((self.problem["people_number"] - 1) / 4) + 1
            info[0]["cost"] = info[0]["price"] * info[0]["cars"]
        elif info[0]["mode"] == "walk":
            info[0]["price"] = info[0]["cost"]

        return info

    def solve(self, problem, prob_idx, oracle_verifier):
        
        sys.stdout = Logger(
            "{}/problem_{}.log".format(
                self.log_dir, problem["uid"]
            ),
            sys.stdout,
            debug_mode=True,
        )
        sys.stderr = Logger(
            "{}/problem_{}.error".format(
                self.log_dir, problem["uid"]
            ),
            sys.stderr,
            debug_mode=True,
        )

        self.reset_clock()
    

        self.problem = problem

        self.backbone_llm.input_token_count = 0
        self.backbone_llm.output_token_count = 0
        
        self.backbone_llm.input_token_maxx = 0


        self.llm_inference_time = 0
        self.information_collection_time = 0
        self.memory = {}

        source_city = problem["start_city"]
        target_city = problem["target_city"]

        print(source_city, "->", target_city)
        self.memory["train_go"] = self.collect_intercity_transport(source_city, target_city, "train")
        self.memory["train_back"] = self.collect_intercity_transport(target_city, source_city, "train")
        self.memory["flight_go"] = self.collect_intercity_transport(source_city, target_city, "airplane")
        self.memory["flight_back"] = self.collect_intercity_transport(target_city, source_city, "airplane")
        
        
        self.memory["accommodations"] = self.collect_poi_info_all(
            problem["target_city"], "accommodation"
        )
        self.memory["attractions"] = self.collect_poi_info_all(
            problem["target_city"], "attraction"
        )
        self.memory["restaurants"] = self.collect_poi_info_all(
            problem["target_city"], "restaurant"
        )

        # print(self.memory)
        selected_go_train_index, selected_go_flight_index = self.select_intercity_transport_go(self.memory["train_go"], self.memory["flight_go"], problem, required_num=self.num_candidates_intercity_transports)        
        selected_back_train_index, selected_back_flight_index = self.select_intercity_transport_back(self.memory["train_back"], self.memory["flight_back"], problem, required_num=self.num_candidates_intercity_transports)
        
        if len(selected_go_train_index) > 0: 
            selected_go_train = self.memory["train_go"].iloc[selected_go_train_index].to_csv(sep='\t', na_rep='nan', index=False)
        else:
            selected_go_train = "None"
        if len(selected_go_flight_index) > 0:
            selected_go_flight = self.memory["flight_go"].iloc[selected_go_flight_index].to_csv(sep='\t', na_rep='nan', index=False)
        else:
            selected_go_flight = "None"
        if len(selected_back_train_index) > 0:
            selected_back_train = self.memory["train_back"].iloc[selected_back_train_index].to_csv(sep='\t', na_rep='nan', index=False)
        else:
            selected_back_train = "None"
        if len(selected_back_flight_index) > 0:
            selected_back_flight = self.memory["flight_back"].iloc[selected_back_flight_index].to_csv(sep='\t', na_rep='nan', index=False)
        else:
            selected_back_flight = "None"

        print("selected go transport: \n", selected_go_train, "\n", selected_go_flight)
        print("selected back transport: \n", selected_back_train, "\n", selected_back_flight)

        selected_accommodation_index = self.select_accommodation(self.memory["accommodations"], problem, required_num=self.num_candidates_accommodations)
        selected_hotel_info = self.memory["accommodations"].iloc[selected_accommodation_index].drop(["id", "hotelname_en"], axis=1).to_csv(sep='\t', na_rep='nan', index=False)
        print("selected hotel: \n", selected_hotel_info)

        selected_attraction_index = self.select_attraction(self.memory["attractions"], problem, required_num=self.num_candidates_attractions)
        selected_attraction_info = self.memory["attractions"].iloc[selected_attraction_index].drop(["id"], axis=1).to_csv(sep='\t', na_rep='nan', index=False)
        print("selected attraction: \n", selected_attraction_info)

        selected_restaurant_index = self.select_restaurant(self.memory["restaurants"], problem, required_num=self.num_candidates_restaurants)
        selected_restaurant_info = self.memory["restaurants"].iloc[selected_restaurant_index].drop(["id"], axis=1).to_csv(sep='\t', na_rep='nan', index=False)
        print("selected restaurant: \n", selected_restaurant_info)
        
        POI_set = set()
        def add_poi_name(df, key):
            if len(df) > 0:
                for item in df[key]:
                    # print(item)
                    POI_set.add(item)
        add_poi_name(self.memory["train_go"].iloc[selected_go_train_index], "To")
        add_poi_name(self.memory["flight_go"].iloc[selected_go_flight_index], "To")
        add_poi_name(self.memory["train_back"].iloc[selected_back_train_index], "From")
        add_poi_name(self.memory["flight_back"].iloc[selected_back_flight_index], "From")
        add_poi_name(self.memory["accommodations"].iloc[selected_accommodation_index], "name")
        add_poi_name(self.memory["attractions"].iloc[selected_attraction_index], "name")
        add_poi_name(self.memory["restaurants"].iloc[selected_restaurant_index], "name")

        POI_list = list(POI_set)
        print(POI_list)

        np.random.seed(19260817)

        print(f"collecting innercity transport for {len(POI_list)} POIs ...")
        
        selected_poi_innercity_transport_list = []
        selected_innercity_transport_info = ""
        for poi_a in tqdm(POI_list):
            for poi_b in POI_list:
                selected_innercity_transport_info += f"from {poi_a} to {poi_b}: "
                for trans_type in ["metro", "taxi", "walk"]:
                    time_str = f"{np.random.randint(10, 20):02d}:{np.random.randint(0, 59):02d}"
                    transports_sel = self.collect_innercity_transport(
                                        target_city,
                                        poi_a,
                                        poi_b,
                                        time_str,
                                        trans_type,
                                        )
                    if transports_sel == "No solution":
                        continue
                    selected_poi_innercity_transport_list.append((poi_a, poi_b, trans_type, transports_sel))
                    if len(transports_sel) > 0:
                        duration = calc_time_delta(transports_sel[0]["start_time"], transports_sel[-1]["end_time"])
                        cost = 0
                        for item in transports_sel:
                            cost += item["cost"]
                        selected_innercity_transport_info += f"{trans_type}: duration {duration}, cost {cost}. "
                    else:
                        selected_innercity_transport_info += f" {trans_type}: empty. "
                selected_innercity_transport_info += "\n"
        
        # for poi_a, poi_b, trans_type, transport_c in selected_poi_innercity_transport_list:
        #     if len(transport_c) > 0:
        #         start_time = transport_c[0]["start_time"]
        #         end_time = transport_c[-1]["end_time"]
        #         cost = 0
        #         for item in transport_c:
        #             cost += item["cost"]
        #         selected_innercity_transport_info += f"from {poi_a} to {poi_b}, {trans_type}: start_time {start_time}, end_time {end_time}, cost {cost}\n"
        #     else:
        #         selected_innercity_transport_info += f"from {poi_a} to {poi_b}, {trans_type}: None\n"
        
        # print(selected_innercity_transport_info)

        self.information_collection_time = time.time() - self.start_clock
        
        # query LLM to get initial solution



        query_message = INITIAL_PROMPT.format(
            go_train_info=selected_go_train, 
            go_flight_info=selected_go_flight, 
            back_train_info=selected_back_train,
            back_flight_info=selected_back_flight,
            attraction_info=selected_attraction_info,
            restaurant_info=selected_restaurant_info,
            accommodation_info=selected_hotel_info,
            innercity_transport_info=selected_innercity_transport_info,
            query=problem['nature_language'])
        
        # print(query_message)

        
        prompt_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_0_prompt.txt')
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(query_message)

        pre_time = time.time()
        response = self.backbone_llm([{"role": "user", "content": query_message}],one_line=False)
        self.llm_inference_time += time.time() - pre_time

        # response = """[{'day': 1, 'activities': [{'start_time': '08:00', 'end_time': '08:25', 'start': '上海站', 'end': '苏州站', 'cost': 55.23, 'TrainID': 'G7004', 'type': 'train', 'tickets': 2, 'transports': 'empty'}, {'position': '苏州观前街乐桥地铁站亚朵酒店', 'type': 'accommodation', 'transports': {'from': '苏州站', 'to': '苏州观前街乐桥地铁站亚朵酒店', 'mode': 'metro', 'start_time': '08:25', 'end_time': '08:39', 'cost': 4}, 'room_type': 1, 'cost': 420, 'start_time': '09:00', 'end_time': '24:00', 'rooms': 1}, {'position': '拙政园', 'type': 'attraction', 'transports': {'from': '苏州观前街乐桥地铁站亚朵酒店', 'to': '拙政园', 'mode': 'metro', 'start_time': '09:30', 'end_time': '09:52', 'cost': 4}, 'cost': 80.0, 'tickets': 2, 'start_time': '10:00', 'end_time': '12:00'}, {'position': '珍珠饭店', 'type': 'lunch', 'transports': {'from': '拙政园', 'to': '珍珠饭店', 'mode': 'metro', 'start_time': '12:00', 'end_time': '12:19', 'cost': 4}, 'cost': 188, 'start_time': '12:30', 'end_time': '13:30'}, {'position': '平江路历史街区', 'type': 'attraction', 'transports': {'from': '珍珠饭店', 'to': '平江路历史街区', 'mode': 'walk', 'start_time': '13:30', 'end_time': '13:40', 'cost': 0}, 'cost': 0.0, 'tickets': 2, 'start_time': '13:45', 'end_time': '15:45'}, {'position': '苏州观前街乐桥地铁站亚朵酒店', 'type': 'accommodation', 'transports': {'from': '平江路历史街区', 'to': '苏州观前街乐桥地铁站亚朵酒店', 'mode': 'metro', 'start_time': '15:45', 'end_time': '16:05', 'cost': 4}, 'room_type': 1, 'cost': 420, 'start_time': '16:30', 'end_time': '24:00', 'rooms': 1}]}, {'day': 2, 'activities': [{'position': '虎丘山风景名胜区', 'type': 'attraction', 'transports': {'from': '苏州观前街乐桥地铁站亚朵酒店', 'to': '虎丘山风景名胜区', 'mode': 'metro', 'start_time': '09:00', 'end_time': '09:28', 'cost': 6}, 'cost': 70.0, 'tickets': 2, 'start_time': '09:30', 'end_time': '11:30'}, {'position': '孙盛兴奥灶面馆(山塘街店)', 'type': 'lunch', 'transports': {'from': '虎丘山风景名胜区', 'to': '孙盛兴奥灶面馆(山塘街店)', 'mode': 'metro', 'start_time': '11:30', 'end_time': '11:45', 'cost': 4}, 'cost': 114, 'start_time': '12:00', 'end_time': '13:00'}, {'position': '苏州古运河游船(山塘街白居易码头)', 'type': 'attraction', 'transports': {'from': '孙盛兴奥灶面馆(山塘街店)', 'to': '苏州古运河游船(山塘街白居易码头)', 'mode': 'walk', 'start_time': '13:00', 'end_time': '13:10', 'cost': 0}, 'cost': 190.0, 'tickets': 2, 'start_time': '13:15', 'end_time': '15:15'}, {'position': '苏州观前街乐桥地铁站亚朵酒店', 'type': 'accommodation', 'transports': {'from': '苏州古运河游船(山塘街白居易码头)', 'to': '苏州观前街乐桥地铁站亚朵酒店', 'mode': 'metro', 'start_time': '15:15', 'end_time': '15:36', 'cost': 4}, 'room_type': 1, 'cost': 420, 'start_time': '16:00', 'end_time': '24:00', 'rooms': 1}]}, {'day': 3, 'activities': [{'position': '苏州博物馆', 'type': 'attraction', 'transports': {'from': '苏州观前街乐桥地铁站亚朵酒店', 'to': '苏州博物馆', 'mode': 'metro', 'start_time': '09:00', 'end_time': '09:23', 'cost': 6}, 'cost': 0.0, 'tickets': 2, 'start_time': '09:30', 'end_time': '11:30'}, {'position': '得月楼(观前店)', 'type': 'lunch', 'transports': {'from': '苏州博物馆', 'to': '得月楼(观前店)', 'mode': 'metro', 'start_time': '11:30', 'end_time': '11:48', 'cost': 4}, 'cost': 306, 'start_time': '12:00', 'end_time': '13:00'}, {'position': '苏州站', 'type': 'train', 'transports': {'from': '得月楼(观前店)', 'to': '苏州站', 'mode': 'metro', 'start_time': '13:00', 'end_time': '13:09', 'cost': 4}, 'start_time': '14:00', 'end_time': '14:30', 'TrainID': 'G7029', 'cost': 110.46, 'tickets': 2}]}]
        # """
        # print(response)
        
        response = """[{"day": 1,""" + response
        nl_plan = repair_json(response)
        # print(nl_plan)
        json_plan = json.loads(nl_plan)


        evaluated_plan = {
            "people_number": problem["people_number"],
            "start_city": problem["start_city"],
            "target_city": problem["target_city"],
            "itinerary": json_plan, 
            
            "elapsed_time(sec)": time.time() - self.start_clock, 
            "input_token_count": self.backbone_llm.input_token_count,
            "output_token_count": self.backbone_llm.output_token_count,
            "input_token_maxx": self.backbone_llm.input_token_maxx,
            "llm_inference_time(sec)": self.llm_inference_time, 
            "information_collection_time": self.information_collection_time, 
        }

        print(json_plan)

        # get error info from symbolic feedback
        error_info = collect_commonsense_constraints_error(problem, evaluated_plan, verbose=False)

        if not "Format Error. Please strictly follow the instructions in the prompt." in error_info:

            try:
                evaluated_plan['itinerary'] = self.translate_innercity_transport(evaluated_plan['itinerary'], problem)
                personal_error_info = collect_personal_error(problem, evaluated_plan, verbose=False)

                for pe in personal_error_info:
                    error_info.append(pe)
            except Exception as e:
                print("Error in translating innercity transport: ", e)
                error_info.append("Format Error on Innercity Transport Information. Please strictly follow the instructions in the prompt.")

        
        print("ITER: ", 0, "ERROR:\n", error_info)

        # exit(0)

        evaluated_plan["error_info"] = error_info

        json_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_0_plan.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(evaluated_plan, f, indent=4, ensure_ascii=False)

        unique_error_info = list(set(error_info))
        error_info_nl = ""
        for item in unique_error_info:
            error_info_nl += item + "\n"
        
        error_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_0_error.err')
        with open(error_file, 'w', encoding='utf-8') as f:
            f.write(error_info_nl)
        
        for step_i in range(1, self.max_steps + 1):            
            

            if (len(error_info) == 0):
                break
                
            # refine the plan with error information
            
            query_message = BACK_PROMPT.format(
            go_train_info=selected_go_train, 
            go_flight_info=selected_go_flight, 
            back_train_info=selected_back_train,
            back_flight_info=selected_back_flight,
            attraction_info=selected_attraction_info,
            restaurant_info=selected_restaurant_info,
            accommodation_info=selected_hotel_info,
            innercity_transport_info=selected_innercity_transport_info,
            query=problem['nature_language'],
            plan=response,
            backprompt=error_info_nl
            )
            
            # print(query_message)
            
            prompt_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_{step_i}_prompt.txt')
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(query_message)
            
            pre_time = time.time()
            response = self.backbone_llm([{"role": "user", "content": query_message}],one_line=False)
            response = """[{"day": 1,""" + response
            
            self.llm_inference_time += time.time() - pre_time

            nl_plan = repair_json(response)
            json_plan = json.loads(nl_plan)

            # print(json_plan)

            evaluated_plan = {
                "people_number": problem["people_number"],
                "start_city": problem["start_city"],
                "target_city": problem["target_city"],
                "itinerary": json_plan, 
                
                "elapsed_time(sec)": time.time() - self.start_clock, 
                "input_token_count": self.backbone_llm.input_token_count,
                "output_token_count": self.backbone_llm.output_token_count,
                "input_token_maxx": self.backbone_llm.input_token_maxx,
                "llm_inference_time(sec)": self.llm_inference_time, 
                "information_collection_time": self.information_collection_time, 
            }
            error_info = collect_commonsense_constraints_error(problem, evaluated_plan, verbose=False)       

            if not "Format Error. Please strictly follow the instructions in the prompt." in error_info:
                try:
                    evaluated_plan['itinerary'] = self.translate_innercity_transport(evaluated_plan['itinerary'], problem)
                    personal_error_info = collect_personal_error(problem, evaluated_plan, verbose=False)
                
                    for pe in personal_error_info:
                        error_info.append(pe)
                
                except Exception as e:
                    print("Error in translating innercity transport: ", e)
                    error_info.append("Format Error on Innercity Transport Information. Please strictly follow the instructions in the prompt.")


            print("ITER: ", step_i, "ERROR:\n", error_info)
            
            evaluated_plan["error_info"] = error_info
    

            json_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_{step_i}_plan.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(evaluated_plan, f, indent=4, ensure_ascii=False)

            error_info_nl = ""
            for item in error_info:
                error_info_nl += item + "\n"
            
            error_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_{step_i}_error.err')
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(error_info_nl)


        return True, evaluated_plan

    def select_accommodation(self, hotel_info, query, required_num=10):
        
        # print(hotel_info.head())
        
        hotel_info = hotel_info.drop(columns=["hotelname_en"])

        # 将 hotel_info 转换为不带索引的字符串
        hotel_info_str = hotel_info.to_csv(sep='\t', na_rep='nan', index=False)

        # print(hotel_info_str)

        time_before = time.time()
        # filtering hotel info by llm
        query_message=[{"role": "user", "content": HOTEL_SELECTION_INSTRUCTION.format(required_options=required_num, user_requirements=query["nature_language"], hotel_info=hotel_info_str)}]

        # print(query_message[0]["content"])

        answer = self.backbone_llm(query_message,one_line=False)


        self.llm_inference_time_count += time.time() - time_before

        print(answer)
        # match = re.search(r'\s*\[(.*?)\]', answer, re.DOTALL)
        
        selected_idx = []
        # if match:
        try:
            HotelNameList = ast.literal_eval(answer)
    
            print('selected HotelNameList: ',HotelNameList) 
            for cand_i in HotelNameList:
                np_where = np.where(hotel_info['name']==cand_i)[0]
                if len(np_where) > 0:
                    selected_index = np_where[0]
                    selected_idx.append(selected_index)
        except Exception as e:
            print("!!!Error in eval HotelNameList:", str(e))
            
            np.random.seed(19260817)
            selected_idx = np.random.choice(len(hotel_info), required_num, replace=False)

        if len(selected_idx) > required_num:
            selected_idx = selected_idx[:required_num]
        return selected_idx
    
    def select_attraction(self, attraction_info, query, required_num=50):

        # print(attraction_info.head())

        attraction_info = attraction_info
        # 将 attraction_info 转换为不带索引的字符串
        attraction_info_str = attraction_info.to_csv(sep='\t', na_rep='nan', index=False)

        # print(attraction_info_str)

        time_before = time.time()
        query_message=[{"role": "user", "content": ATTRACTION_SELECTION_INSTRUCTION.format(required_options=required_num, user_requirements=query["nature_language"], attraction_info=attraction_info_str)}]

        answer = self.backbone_llm(query_message,one_line=False)
        
        print(answer)

        time_after = time.time()
        selected_idx = []

        try:
            AttrNameList = ast.literal_eval(answer)
            print('selected AttrNameList: ',AttrNameList) 
            for cand_i in AttrNameList:
                np_where = np.where(attraction_info['name']==cand_i)[0]
                if len(np_where) > 0:
                    selected_index = np_where[0]
                selected_idx.append(selected_index)

        except Exception as e:
            print("!!!Error in eval selected_idx:", str(e))

            np.random.seed(19260817)
            selected_idx = np.random.choice(len(attraction_info), required_num, replace=False)

        if len(selected_idx) > required_num:
            selected_idx = selected_idx[:required_num]
        return selected_idx
    def select_restaurant(self, restaurant_info, query, required_num=30):


        restaurant_info_str = restaurant_info.to_csv(sep='\t', na_rep='nan', index=False)

        # print(restaurant_info_str)

        time_before = time.time()
        query_message=[{"role": "user", "content": RESTAURANT_SELECTION_INSTRUCTION.format(required_options=required_num, user_requirements=query["nature_language"], restaurant_info=restaurant_info_str)}]

        answer = self.backbone_llm(query_message,one_line=False)

        print(answer)

        time_after = time.time()
        selected_idx = []

        try:
            RestNameList = ast.literal_eval(answer)
            print('selected RestNameList: ',RestNameList) 
            for cand_i in RestNameList:
                np_where = np.where(restaurant_info['name']==cand_i)[0]
                if len(np_where) > 0:
                    selected_index = np_where[0]
                    selected_idx.append(selected_index)

        except Exception as e:
            print("!!!Error in eval selected_idx:", str(e))

            np.random.seed(19260817)
            selected_idx = np.random.choice(len(restaurant_info), required_num, replace=False)

        if len(selected_idx) > required_num:
            selected_idx = selected_idx[:required_num]
        return selected_idx
    
    def select_intercity_transport_go(self, train_info, flight_info, query, required_num=10):
        train_info_str = train_info.to_csv(sep='\t', na_rep='nan', index=False)
        flight_info_str = flight_info.to_csv(sep='\t', na_rep='nan', index=False)
        time_before = time.time()

        query_message=[{"role": "user", "content": TRANSPORT_GO_SELECTION_INSTRUCTION.format(origin=query["start_city"], destination=query["target_city"], required_options=required_num, user_requirements=query["nature_language"], train_info=train_info_str, flight_info=flight_info_str)}]
        answer = self.backbone_llm(query_message,one_line=False)
        print(answer)

        selected_train_idx, selected_flight_idx = [], []
        try:
            TransportList = ast.literal_eval(answer)
            print('selected TransportList: ',TransportList) 
            for cand_i in TransportList:

                if (len(train_info)>0):
                    np_where = np.where(train_info['TrainID']==cand_i)[0]
                    if len(np_where) > 0:
                        selected_train_idx.append(np_where[0])
                        
                if (len(flight_info)>0):
                    np_where = np.where(flight_info['FlightID']==cand_i)[0]
                    if len(np_where) > 0:
                        selected_flight_idx.append(np_where[0])
            if len(selected_train_idx) > required_num:
                selected_train_idx = selected_train_idx[:required_num]
            if len(selected_flight_idx) > required_num:
                selected_flight_idx = selected_flight_idx[:required_num]

        except Exception as e:
            print("!!!Error in eval selected_idx:", str(e))
            np.random.seed(19260817)
            selected_train_idx = np.random.choice(len(train_info), min(len(train_info), required_num // 2), replace=False)
            selected_flight_idx = np.random.choice(len(flight_info), min(len(flight_info), required_num - required_num // 2), replace=False)         

        return selected_train_idx, selected_flight_idx

    def select_intercity_transport_back(self, train_info, flight_info, query, required_num=10):
        train_info_str = train_info.to_csv(sep='\t', na_rep='nan', index=False)
        flight_info_str = flight_info.to_csv(sep='\t', na_rep='nan', index=False)
        time_before = time.time()
        query_message=[{"role": "user", "content": TRANSPORT_BACK_SELECTION_INSTRUCTION.format(origin=query["target_city"], destination=query["start_city"], required_options=required_num, user_requirements=query["nature_language"], train_info=train_info_str, flight_info=flight_info_str)}]
        answer = self.backbone_llm(query_message,one_line=False)
        print(answer)
        selected_train_idx, selected_flight_idx = [], []
        try:
            TransportList = ast.literal_eval(answer)
            print('selected TransportList: ',TransportList)
            for cand_i in TransportList:
                if (len(train_info)>0):
                    np_where = np.where(train_info['TrainID']==cand_i)[0]
                    if len(np_where) > 0:
                        selected_train_idx.append(np_where[0])

                if (len(flight_info)>0):
                    np_where = np.where(flight_info['FlightID']==cand_i)[0]
                    if len(np_where) > 0:
                        selected_flight_idx.append(np_where[0])

            if len(selected_train_idx) > required_num:
                selected_train_idx = selected_train_idx[:required_num]
            if len(selected_flight_idx) > required_num:
                selected_flight_idx = selected_flight_idx[:required_num]
                
        except Exception as e:
            print("!!!Error in eval selected_idx:", str(e))
            np.random.seed(19260817)
            selected_train_idx = np.random.choice(len(train_info), min(len(train_info), required_num // 2), replace=False)
            selected_flight_idx = np.random.choice(len(flight_info), min(len(flight_info), required_num - required_num // 2), replace=False)

        return selected_train_idx, selected_flight_idx

    def translate_innercity_transport(self, plan, problem):
        
        # print("Translating...")
        # print(plan)

        for day_activity in plan:
            for activity in day_activity['activities']:
                if 'transports' in activity:
                    if type(activity['transports']) == dict:
                        try:
                            activity['transports']['from']
                            activity['transports']['to']
                            activity['transports']['start_time']
                            activity['transports']['end_time']
                            activity['transports']['mode']
                            activity['transports']['cost']
                            call_str = (
                                    'goto("{city}", "{start}", "{end}", "{start_time}", "{trans_type}")'.format(
                                        city=problem["target_city"],
                                        start=activity['transports']['from'],
                                        end=activity['transports']['to'],
                                        start_time=activity['transports']['start_time'],
                                        trans_type=activity['transports']['mode'], 
                                    )
                                )
                            info = self.env(call_str)["data"]
                            if len(info) == 3:
                                info[1]["price"] = info[1]["cost"]
                                info[1]["tickets"] = self.problem["people_number"]
                                # info[1]["cost"] = info[1]["price"] * info[1]["tickets"]
                                info[1]["cost"] = activity['transports']['cost']
                                

                                info[0]["price"] = info[0]["cost"]
                                info[2]["price"] = info[2]["cost"]
                            elif info[0]["mode"] == "taxi":
                                info[0]["price"] = info[0]["cost"]
                                info[0]["cars"] = int((self.problem["people_number"] - 1) / 4) + 1
                                # info[0]["cost"] = info[0]["price"] * info[0]["cars"]
                                info[0]["cost"] = activity['transports']['cost']

                            elif info[0]["mode"] == "walk":
                                # info[0]["price"] = info[0]["cost"]
                                info[0]["cost"] = activity['transports']['cost']

                            activity['transports'] = info
                    
                        except:
                            activity['transports'] = []
                            continue
                    else:
                        activity['transports'] = []
                    

        # print("TRANSFERED:")
        # print(plan)

        # exit(0)

        return plan
