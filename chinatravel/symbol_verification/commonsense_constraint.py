import sys


from chinatravel.environment.tools.accommodations.apis import Accommodations
from chinatravel.environment.tools.restaurants.apis import Restaurants
from chinatravel.environment.tools.attractions.apis import Attractions
from chinatravel.environment.tools.intercity_transport.apis import IntercityTransport
from chinatravel.environment.tools.transportation.apis import Transportation
from chinatravel.environment.language import CITY_NAMES, normalize_lang
from chinatravel.symbol_verification.concept_func import normalize_poi_name

# from env.tools.transportation.apis import GoTo
# from envs import goto
import json
import os
import sys
from tqdm import tqdm

from chinatravel.evaluation.utils import load_json_file

import pandas as pd

accommodation = Accommodations()
restaurants = Restaurants()
attractions = Attractions()
intercity_transport=IntercityTransport()
innercity_transport=Transportation()
_TOOLS_BY_LANG = {
    "zh": (
        accommodation,
        restaurants,
        attractions,
        intercity_transport,
        innercity_transport,
    )
}


def _infer_lang(symbolic_input):
    city_values = {
        symbolic_input.get("start_city"),
        symbolic_input.get("target_city"),
    }
    if city_values & set(CITY_NAMES["en"]):
        return "en"
    return "zh"


def _set_tool_lang(lang):
    global accommodation, restaurants, attractions, intercity_transport, innercity_transport
    lang = normalize_lang(lang)
    if lang not in _TOOLS_BY_LANG:
        _TOOLS_BY_LANG[lang] = (
            Accommodations(lang=lang),
            Restaurants(lang=lang),
            Attractions(lang=lang),
            IntercityTransport(lang=lang),
            Transportation(lang=lang),
        )
    (
        accommodation,
        restaurants,
        attractions,
        intercity_transport,
        innercity_transport,
    ) = _TOOLS_BY_LANG[lang]


'''
Constraints:
Available
1. Intercity transport information exsits and is objective: ID, time, startpos and endpos need to be correct.
2. Attractions
3. Hotels
4. Restaurants
5. transportation
6. Times
7. space
'''

_INTERCITY_ACTIVITY_TYPES = {"airplane", "train"}
_POSITION_ACTIVITY_TYPES = {"attraction", "breakfast", "lunch", "dinner", "accommodation"}


def return_info_debug(flag, info):
    return flag, info


def return_info_test(flag, info):
    return flag


def Is_activity_grounded(symbolic_input, plan_json, verbose=False):
    
    table_statistics = pd.DataFrame(columns=['Invalid or ungrounded activity entity'])

    error_info = []

    if not isinstance(plan_json, dict):
        table_statistics.loc[0] = [1]
        error_info = ["Error plan type, must be python dict"]
        return table_statistics, error_info
    try:
        plan = plan_json["itinerary"]
    except:
        table_statistics.loc[0] = [1]
        error_info = ["Error plan type, must provide itinerary"]
        return table_statistics, error_info

    table_statistics.loc[0] = [0]

    if not isinstance(plan, list) or len(plan) == 0:
        table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
        error_info.append("Itinerary must be a non-empty list.")
        return table_statistics, error_info

    last_day_idx = len(plan) - 1
    for day_idx, day_plan_i in enumerate(plan):
        activities = day_plan_i.get("activities", []) if isinstance(day_plan_i, dict) else []
        if not isinstance(activities, list):
            table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
            error_info.append("Each itinerary day must provide an activities list.")
            continue

        last_activity_idx = len(activities) - 1
        for activity_idx, activity_i in enumerate(activities):
            if not isinstance(activity_i, dict):
                table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
                error_info.append("Each activity must be a dict.")
                continue

            activity_type = activity_i.get("type")
            is_first_activity = day_idx == 0 and activity_idx == 0
            is_last_activity = day_idx == last_day_idx and activity_idx == last_activity_idx

            if activity_type in _INTERCITY_ACTIVITY_TYPES:
                if not (is_first_activity or is_last_activity):
                    table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
                    error_info.append("Intercity transport can only appear as the first or last activity: " + str(activity_i))

                if activity_i.get("position"):
                    table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
                    error_info.append("Intercity transport must not provide a POI position: " + str(activity_i))

                required_id = "FlightID" if activity_type == "airplane" else "TrainID"
                forbidden_id = "TrainID" if activity_type == "airplane" else "FlightID"
                if required_id not in activity_i:
                    table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
                    error_info.append("Intercity transport misses {}: ".format(required_id) + str(activity_i))
                if forbidden_id in activity_i:
                    table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
                    error_info.append("Intercity transport has mismatched id field {}: ".format(forbidden_id) + str(activity_i))
                if "start" not in activity_i or "end" not in activity_i:
                    table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
                    error_info.append("Intercity transport must provide start and end: " + str(activity_i))
                continue

            if activity_type not in _POSITION_ACTIVITY_TYPES:
                table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
                error_info.append("Unknown activity type: " + str(activity_i))
                continue

            if not activity_i.get("position"):
                table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
                error_info.append("POI activity must provide a position: " + str(activity_i))

            forbidden_keys = [key for key in ("start", "end", "TrainID", "FlightID") if key in activity_i]
            if forbidden_keys:
                table_statistics.loc[0, 'Invalid or ungrounded activity entity'] = 1
                error_info.append("POI activity must not provide intercity fields {}: ".format(forbidden_keys) + str(activity_i))

    if verbose:
        if table_statistics.loc[0].sum() == 0:
            print("Activity grounding passed!")
        else:
            print(error_info)
            print(table_statistics)
    return table_statistics, error_info



def Is_intercity_transport_correct(symbolic_input, plan_json, verbose=False):
    
    # print("input: ", symbolic_input)
    # print("plan: ", plan_json)
    
    table_statistics = pd.DataFrame(columns=['Intercity transportation events must occur', 'Invalid Trains or Airplanes, given TrainID/FlightID, origin and destination', 'Incorrect Information of Intercity Transport on price or duration', 'Incorrect Cost on Intercity Transportation'])

    error_info = []

    if not isinstance(plan_json, dict):
        table_statistics.loc[0] = [1, 1, 1, 1]
        error_info = ["Error plan type, must be python dict"]
        return table_statistics, error_info
    try:plan_json["itinerary"]
    except:
        table_statistics.loc[0] = [1, 1, 1, 1]
        error_info = ["Error plan type, must provide itinerary"]
        return table_statistics, error_info
    
    first_day_plan=plan_json["itinerary"][0]
    last_day_plan=plan_json["itinerary"][-1]

    target_city=symbolic_input['target_city']
    start_pos=symbolic_input['start_city']

    # must contain intecity transport
    if len(first_day_plan["activities"])==0 or len(last_day_plan["activities"])==0: 
        table_statistics.loc[0] = [1, 1, 1, 1]
        error_info = ["It must contain intecity transport"]
        return table_statistics, error_info
    

    go_intercity_transport_plan=first_day_plan["activities"][0]
    back_intercity_transport_plan=last_day_plan["activities"][-1]
    if("FlightID" not in go_intercity_transport_plan.keys()) and ("TrainID" not in go_intercity_transport_plan.keys()): 
        # return return_info(False, "The first activity should be a transport.") # "The first transport should be from origin to destination.")
        table_statistics.loc[0] = [1, 1, 1, 1]
        error_info = ["The first activity should be an intercity transport."]
        return table_statistics, error_info
    
    if("FlightID" not in back_intercity_transport_plan.keys()) and ("TrainID" not in back_intercity_transport_plan.keys()): 
        # return return_info(False, "The last activity should be a transport.") # "The last transport should be from destination to origin.")
        table_statistics.loc[0] = [1, 1, 1, 1]
        error_info = ["The last activity should be an intercity transport."]
        return table_statistics, error_info


    go_type=go_intercity_transport_plan['type']
    if go_type!='airplane' and go_type!='train':
        # return return_info(False, "Intercity transport type should be airplane or train")
        table_statistics.loc[0] = [0, 1, 1, 1]
        error_info = ["Intercity transport type should be airplane or train in the sandbox."]
        return table_statistics, error_info
    
    back_type=back_intercity_transport_plan['type']
    if back_type!='airplane' and back_type!='train':
        # return return_info(False, "Intercity transport type should be airplane or train")
        table_statistics.loc[0] = [0, 1, 1, 1]
        error_info = ["Intercity transport type should be airplane or train in the sandbox."]
        return table_statistics, error_info
    

    table_statistics.loc[0] = [0, 0, 0, 0]

    go_df=intercity_transport.select(start_pos,target_city,go_type)

    if not ("start" in go_intercity_transport_plan and "end" in go_intercity_transport_plan):
        # return return_info(False, "intercity-transport should provide start and end position.")
        table_statistics.loc[0] = [0, 1, 1, 1]
        error_info.append("Intercity-transport Go should provide start and end position.")
        return table_statistics, error_info
    
    if not ("start" in back_intercity_transport_plan and "end" in back_intercity_transport_plan):
        # return return_info(False, "intercity-transport should provide start and end position.")
        table_statistics.loc[0] = [0, 1, 1, 1]
        error_info.append("Intercity-transport Back should provide start and end position.")
        return table_statistics, error_info
    

    go_flag=0
    for _, row in go_df.iterrows():
        if go_type=='airplane':
            try: 
                go_intercity_transport_plan['FlightID']
            except: 
                table_statistics.loc[0] = [0, 1, 1, 1]
                error_info.append("Iintercity airplane (Go) should provide the valid FlightID.")
                break

            if go_intercity_transport_plan['FlightID']==row['FlightID'] and go_intercity_transport_plan['start']==row['From'] and go_intercity_transport_plan['end']==row['To']:
                go_flag=1
                try: 
                    go_intercity_transport_plan['start_time']
                    go_intercity_transport_plan['end_time']
                    if row['BeginTime'] == go_intercity_transport_plan['start_time'] and row['EndTime'] == go_intercity_transport_plan['end_time']:
                        pass
                    else:
                        table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                        error_info.append("Incorrect duration information of given intercity airplane (Go) [start_time -> end_time].")
                except: 
                    table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                    error_info.append("Iintercity airplane (Go) should provide the duration information.")
                
                try: 
                    go_intercity_transport_plan['price']
                    if row['Cost']==go_intercity_transport_plan['price']:
                        pass                    
                    else:
                        table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                        error_info.append("Incorrect price information of given intercity airplane [origin -> destination].")
                except: 
                    table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                    error_info.append("Iintercity airplane (Go) should provide the price information.")
                

                try:
                    go_intercity_transport_plan['tickets']
                    go_intercity_transport_plan['cost']
                    if abs(go_intercity_transport_plan['price'] * go_intercity_transport_plan['tickets'] - go_intercity_transport_plan['cost']) > .1:
                        table_statistics.loc[0,  "Incorrect Cost on Intercity Transportation"] = 1
                        error_info.append("Incorrect cost information of given intercity airplane (Go) [cost = price * tickets].")
                except: 
                    table_statistics.loc[0,  "Incorrect Cost on Intercity Transportation"] = 1
                    error_info.append("Iintercity airplane (Go) should provide the tickets and cost information.")

                break
        if go_type=='train':
            try: 
                go_intercity_transport_plan['TrainID']
            except: 
                table_statistics.loc[0] = [0, 1, 1, 1]
                error_info.append("Iintercity train (Go) should provide the valid TrainID.")
                break

            if go_intercity_transport_plan['TrainID']==row['TrainID']  and go_intercity_transport_plan['start']==row['From'] and go_intercity_transport_plan['end']==row['To']:
                go_flag=1
                try: 
                    go_intercity_transport_plan['start_time']
                    go_intercity_transport_plan['end_time']
                    if row['BeginTime'] == go_intercity_transport_plan['start_time'] and row['EndTime'] == go_intercity_transport_plan['end_time']:
                        pass
                    else:
                        table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                        error_info.append("Incorrect duration information of given intercity train (Go) [start_time -> end_time].")
                except: 
                    table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                    error_info.append("Iintercity train (Go) should provide the duration information.")
                
                try: 
                    go_intercity_transport_plan['price']
                    if row['Cost']==go_intercity_transport_plan['price']:
                        pass                    
                    else:
                        table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                        error_info.append("Incorrect price information of given intercity train [origin -> destination].")
                except: 
                    table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                    error_info.append("Iintercity train (Go) should provide the price information.")
                


                try:
                    go_intercity_transport_plan['tickets']
                    go_intercity_transport_plan['cost']
                    if abs(go_intercity_transport_plan['price'] * go_intercity_transport_plan['tickets'] - go_intercity_transport_plan['cost']) > .1:
                        table_statistics.loc[0,  "Incorrect Cost on Intercity Transportation"] = 1
                        error_info.append("Incorrect cost information of given intercity train (Go) [cost = price * tickets].")
                except: 
                    table_statistics.loc[0,  "Incorrect Cost on Intercity Transportation"] = 1
                    error_info.append("Iintercity train (Go) should provide the tickets and cost information.")

                break

    if go_flag==0:
        table_statistics.loc[0] = [0, 1, 1, 1]
        error_info.append("No information found given transport ID.")

    
    back_df=intercity_transport.select(target_city,start_pos,back_type)

    back_flag=0
    
    for _, row in back_df.iterrows():
        if back_type=='airplane':
            try: 
                back_intercity_transport_plan['FlightID']
            except: 
                table_statistics.loc[0] = [0, 1, 1, 1]
                error_info.append("Iintercity airplane (Back) should provide the valid FlightID.")
                break
            if back_intercity_transport_plan['FlightID']==row['FlightID'] and back_intercity_transport_plan['start']==row['From'] and back_intercity_transport_plan['end']==row['To']:
                back_flag=1
                try: 
                    back_intercity_transport_plan['start_time']
                    back_intercity_transport_plan['end_time']
                    if row['BeginTime'] == back_intercity_transport_plan['start_time'] and row['EndTime'] == back_intercity_transport_plan['end_time']:
                        pass
                    else:
                        table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                        error_info.append("Incorrect duration information of given intercity airplane (Back) [start_time -> end_time].")
                except: 
                    table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                    error_info.append("Iintercity airplane (Back) should provide the duration information.")
                
                try: 
                    back_intercity_transport_plan['price']
                    if row['Cost']==back_intercity_transport_plan['price']:
                        pass                    
                    else:
                        table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                        error_info.append("Incorrect price information of given intercity airplane [destination -> origin].")
                except: 
                    table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                    error_info.append("Iintercity airplane (Back) should provide the price information.")

                
                try:
                    back_intercity_transport_plan['tickets']
                    back_intercity_transport_plan['cost']
                    if abs(back_intercity_transport_plan['price'] * back_intercity_transport_plan['tickets'] - back_intercity_transport_plan['cost']) > .1:
                        table_statistics.loc[0,  "Incorrect Cost on Intercity Transportation"] = 1
                        error_info.append("Incorrect cost information of given intercity airplane (Back) [cost = price * tickets].")
                except: 
                    table_statistics.loc[0,  "Incorrect Cost on Intercity Transportation"] = 1
                    error_info.append("Iintercity airplane (Back) should provide the tickets and cost information.")
                break

        if back_type=='train':
            try: 
                back_intercity_transport_plan['TrainID']
            except: 
                table_statistics.loc[0] = [1, 1, 1, 1]
                error_info.append("Iintercity train (Back) should provide the valid TrainID.")
                break
                
            
            if back_intercity_transport_plan['TrainID']==row['TrainID'] and back_intercity_transport_plan['start']==row['From'] and back_intercity_transport_plan['end']==row['To']:
                back_flag=1
                try: 
                    back_intercity_transport_plan['start_time']
                    back_intercity_transport_plan['end_time']
                    if row['BeginTime'] == back_intercity_transport_plan['start_time'] and row['EndTime'] == back_intercity_transport_plan['end_time']:
                        pass
                    else:
                        table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                        error_info.append("Incorrect time information of given intercity train [destination -> origin].")
                except: 
                    table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                    error_info.append("Iintercity train (Back) should provide the duration information.")

                try: 
                    back_intercity_transport_plan['price']
                    if row['Cost']==back_intercity_transport_plan['price']:
                        pass                    
                    else:
                        table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                        error_info.append("Incorrect price information of given intercity train [origin -> destination].")
                except: 
                    table_statistics.loc[0,  "Incorrect Information of Intercity Transport on price or duration"] = 1
                    error_info.append("Iintercity train (Back) should provide the price information.")

                try:
                    back_intercity_transport_plan['tickets']
                    back_intercity_transport_plan['cost']
                    if abs(back_intercity_transport_plan['price'] * back_intercity_transport_plan['tickets'] - back_intercity_transport_plan['cost']) > .1:
                        table_statistics.loc[0,  "Incorrect Cost on Intercity Transportation"] = 1
                        error_info.append("Incorrect cost information of given intercity train (Back) [cost = price * tickets].")
                except: 
                    table_statistics.loc[0,  "Incorrect Cost on Intercity Transportation"] = 1
                    error_info.append("Iintercity train (Back) should provide the tickets and cost information.")

                break
    
    if back_flag==0:
        table_statistics.loc[0] = [0, 1, 1, 1]
        error_info.append("No information found given transport ID.")

    if verbose:
        if table_statistics.loc[0].sum() == 0:
            print("Intercity_transport passed!")
        else:
            print(error_info)
            print(table_statistics)
    return table_statistics, error_info


def Is_attractions_correct(symbolic_input, plan_json, verbose=False):
    
    
    target_city = symbolic_input["target_city"]


    table_statistics = pd.DataFrame(columns=['Unavailable attractions', 'Visiting attraction in their closed time', 'Repeated attraction Choices', 'Incorrect price Information of attraction', 'Incorrect cost Information of attraction'])

    error_info = []    
    try: 
        plan_json["itinerary"]
    except: 
        table_statistics.loc[0] = [1, 1, 1, 1, 1]
        error_info = ["Error plan type, must be python dict"]
        return table_statistics, error_info

    plan = plan_json["itinerary"]
    
    table_statistics.loc[0] = [0, 0, 0, 0, 0]
    attraction_list = []

    for day_plan_i in plan:
        for activity_i in day_plan_i["activities"]:

            try: 
                activity_i["type"]
            except: 
                continue
            if activity_i["type"] != "attraction":
                continue
            
            # print(activity_i)
            try: activity_i["position"]
            except: 
                table_statistics.loc[0] = [1, 1, 1, 1, 1]
                error_info.append("No position information!")
                return table_statistics, error_info
            
            position = normalize_poi_name(activity_i["position"])
            select_attraction=attractions.select(target_city,key='name',func=lambda x:x==position)

            # print(select_attraction)

            if select_attraction.empty:
                table_statistics.loc[0] = [1, 1, 1, 1, 1]
                error_info.append("No information found given attraction [{}]".format(activity_i["position"]))
                return table_statistics, error_info

            else:
                attraction_list.append(position)
            
            # 开放时间
            opentime, endtime = select_attraction["opentime"].values[0],  select_attraction["endtime"].values[0]
            if time_compare_if_earlier_equal(endtime, opentime):
                endtime = str(int(endtime.split(":")[0]) + 24) + ":" + endtime.split(":")[1]
            try: 
                activity_i["start_time"]
                activity_i["end_time"]

                # if time_compare_if_earlier_equal(endtime, activity_i["start_time"]) or time_compare_if_earlier_equal(activity_i["end_time"], opentime): 
                if not (time_compare_if_earlier_equal(opentime, activity_i["start_time"]) and time_compare_if_earlier_equal(activity_i["end_time"], endtime)):
                    # return return_info(False, "The attraction is closed now. {}, open time: [{} -- {}]".format(activity_i["position"], opentime, endtime))
                    table_statistics.loc[0,  'Visiting attraction in their closed time'] = 1
                    error_info.append("The attraction is closed now. {}, open time: [{} -- {}]".format(activity_i["position"], opentime, endtime))
            except:
                table_statistics.loc[0,  'Visiting attraction in their closed time'] = 1
                error_info.append("The activity in attraction shoud provide the visiting time.")

            # 返回信息保证一致: price
            try: 
                activity_i["price"]
                if int(activity_i["price"]) != int(select_attraction["price"].values[0]):
                    # return return_info(False, "Incorrect cost infomation of attraction [{}], cost: {} ".format(activity_i["position"], activity_i["cost"]))
                    table_statistics.loc[0,  'Incorrect price Information of attraction'] = 1
                    error_info.append("Incorrect price infomation of attraction [{}], price: {} ".format(activity_i["position"], activity_i["price"]))
                        
            except: 
                table_statistics.loc[0,  'Incorrect price Information of attraction'] = 1
                error_info.append("Attraction price should be provided")

            
            try: 
                activity_i["tickets"]
                activity_i["cost"]
                if abs(activity_i["price"] * activity_i["tickets"] - activity_i["cost"]) > .1:
                    table_statistics.loc[0,  'Incorrect cost Information of attraction'] = 1
                    error_info.append("Incorrect cost information of attraction [cost = price * tickets].")
                        
            except: 
                table_statistics.loc[0,  'Incorrect cost Information of attraction'] = 1
                error_info.append("Incorrect cost Information of attraction")

            # if not select_attraction_type.empty:
            #     spot_type.add(select_attraction_type.iloc[0])
            # attraction_names.add(activity["position"])

    if len(set(attraction_list)) != len(attraction_list):
        table_statistics.loc[0,  'Repeated attraction Choices'] = 1
        error_info.append("Attraction choices should not be repeated throughout the trip.")

    if verbose:
        if table_statistics.loc[0].sum() == 0:
            print("Attractions passed!")
        else:
            print(error_info)
            print(table_statistics)
    return table_statistics, error_info


def Is_hotels_correct(symbolic_input, plan_json, verbose=False): 

    target_city = symbolic_input["target_city"]
    table_statistics = pd.DataFrame(columns=['Unavailable Accommodation', 'Incorrect Information of Accommodation on price or room type', 'Incorrect cost Information of Accommodation', 'Accomondation is necessary for trips longer than one day'])

    error_info = []    
    try: 
        plan_json["itinerary"]
    except: 
        table_statistics.loc[0] = [1, 1, 1, 1]
        error_info = ["Error plan type, must be python dict"]
        return table_statistics, error_info

    table_statistics.loc[0] = [0, 0, 0, 0]

    plan = plan_json["itinerary"]
    
    hotel_list = []
 
    for day_plan_i in plan:
        for activity_i in day_plan_i["activities"]:

            try: activity_i["type"]
            except: 
                continue
            if activity_i["type"] != "accommodation":
                continue

            # print(activity_i)
            
            try: activity_i["position"]
            except: 
                table_statistics.loc[0] = [1, 1, 1, 1]
                error_info.append("No position information!")
                return table_statistics, error_info
            
            position = normalize_poi_name(activity_i["position"])
            select_hotel=accommodation.select(target_city,key='name',func=lambda x:x==position)
            # print(select_hotel)

            if select_hotel.empty:
                table_statistics.loc[0] = [1, 1, 1, 1]
                error_info.append("No information found given hotel [{}]".format(activity_i["position"]))
                return table_statistics, error_info

            else:
                hotel_list.append(position)

            # 返回信息保证一致: price
            try: 
                activity_i["price"]
                if activity_i["price"] != select_hotel["price"].values[0]:
                    table_statistics.loc[0,  'Incorrect Information of Accommodation on price or room type'] = 1
                    error_info.append("Incorrect price infomation of accommodation [{}], price: {} ".format(activity_i["position"], select_hotel["price"].values[0]))
            
            except: 
                table_statistics.loc[0,  'Incorrect Information of Accommodation on price or room type'] = 1
                error_info.append("Hotel price should be provided")
                

                    
            try: 
                activity_i["room_type"]    
                if activity_i["room_type"] != select_hotel["numbed"].values[0]:
                    table_statistics.loc[0,  'Incorrect Information of Accommodation on price or room type'] = 1
                    error_info.append("Incorrect room infomation of accommodation [{}], numbed: {} ".format(activity_i["position"], select_hotel["numbed"].values[0]))
            except: 
                table_statistics.loc[0,  'Incorrect Information of Accommodation on price or room type'] = 1
                error_info.append("Room information should be provided")
            
            try:
                activity_i["rooms"]
                if abs(activity_i["rooms"] * activity_i["price"] - activity_i["cost"]) > .1:
                    table_statistics.loc[0,  'Incorrect cost Information of Accommodation'] = 1
                    error_info.append("Incorrect cost information of accommodation [cost = price * rooms].")
            except: 
                table_statistics.loc[0,  'Incorrect cost Information of Accommodation'] = 1
                error_info.append("Cost and rooms information should be provided")


    # if len(set(hotel_list)) > 1:
    #     # return return_info(False, "Hotel should be unique during the trip.")
    #     table_statistics.loc[0] = [1, 1, 1]
    #     error_info.append("Hotel should be unique during the trip.")
    
    if len(plan_json["itinerary"]) > 1 and len(hotel_list) == 0:
        table_statistics.loc[0, 'Accomondation is necessary for trips longer than one day'] = 1
        error_info.append("We need a hotel for a trip more than one day.")
        
    if verbose:
        if table_statistics.loc[0].sum() == 0:
            print("Hotels passed!")
        else:
            print(error_info)
            print(table_statistics)
    return table_statistics, error_info

def Is_restaurants_correct(symbolic_input, plan_json, verbose=False): 
    
    target_city = symbolic_input["target_city"]
    table_statistics = pd.DataFrame(columns=['Unavailable Restruants', 'Visiting Restruants in their closed time', 'Repeated Restruants Choices', 'Incorrect price Information of Restruants', 'Incorrect cost Information of Restruants', 'Inappropriate Meal Times'])

    error_info = []    
    try: 
        plan_json["itinerary"]
    except: 
        table_statistics.loc[0] = [1, 1, 1, 1, 1, 1]
        error_info = ["Error plan type, must be python dict"]
        return table_statistics, error_info

    table_statistics.loc[0] = [0, 0, 0, 0, 0, 0]

    plan = plan_json["itinerary"]
    
    restaurants_list = []
    restaurants_time_list = []

    for day_plan_i in plan:
        for activity_i in day_plan_i["activities"]:
            try: activity_i["type"]
            except: continue
            if not activity_i["type"] in ["breakfast", "lunch", "dinner"]:
                continue
            
            # print(activity_i)
            try: activity_i["position"]
            except: 
                table_statistics.loc[0] = [1, 1, 1, 1, 1, 1]
                error_info.append("No position information!")
                return table_statistics, error_info
            

            position = normalize_poi_name(activity_i["position"])
            select_restaurant=restaurants.select(target_city,key='name',func=lambda x:x==position)

            # print(select_restaurant)

            if activity_i["type"] == "breakfast" and select_restaurant.empty:

                select_hotel=accommodation.select(target_city,key='name',func=lambda x:x==position)
    
                if select_hotel.empty:
                    table_statistics.loc[0] = [1, 1, 1, 1, 1, 1]
                    error_info.append("No information found given restaurant [{}]".format(activity_i["position"]))
                try:
                    activity_i["price"]
                    if activity_i["price"] != 0:
                        table_statistics.loc[0,  'Incorrect price Information of Restruants'] = 1
                        error_info.append("Have breakfast at hotel, price 0")
                except: 
                    table_statistics.loc[0,  'Incorrect price Information of Restruants'] = 1
                    error_info.append("price of breakfast should be provided")

                try:
                    activity_i["start_time"]
                    activity_i["end_time"]

                    if time_compare_if_earlier_equal("09:00", activity_i["start_time"]) or time_compare_if_earlier_equal(activity_i["end_time"], "06:00"):
                    
                        table_statistics.loc[0,  'Inappropriate Meal Times'] = 1
                        error_info.append("The time of breakfast should be in [06:00 -- 09:00]")
                except:
                    table_statistics.loc[0,  'Inappropriate Meal Times'] = 1
                    error_info.append("The time of breakfast should be provided")

                try:
                    activity_i["cost"]
                    if abs(symbolic_input["people_number"] * activity_i["price"] - activity_i["cost"]) > .1:
                        table_statistics.loc[0,  'Incorrect cost Information of Restruants'] = 1
                        error_info.append("Incorrect cost information of Restruants Events [cost = price * people_number].")
                except:
                    table_statistics.loc[0,  'Incorrect cost Information of Restruants'] = 1
                    error_info.append("The Restruants Events should provide cost information")

                continue
            
            if select_restaurant.empty:
                # return return_info(False, "No information found given restaurant [{}]".format(activity_i["position"]))
                table_statistics.loc[0] = [1, 1, 1, 1, 1, 1]
                error_info.append("No information found given restaurant [{}]".format(activity_i["position"]))
                continue
            
            try:
                activity_i["price"]
                if activity_i["price"] != select_restaurant["price"].values[0]:
                    table_statistics.loc[0,  'Incorrect price Information of Restruants'] = 1
                    error_info.append("Incorrect price infomation of restaurant [{}], price: {} ".format(activity_i["position"], select_restaurant["price"].values[0]))
            except:
                table_statistics.loc[0,  'Incorrect price Information of Restruants'] = 1
                error_info.append("price of Restruants should be provided")
            
            try:
                activity_i["start_time"]
                activity_i["end_time"]
                if activity_i["type"] == "lunch" and (time_compare_if_earlier_equal("14:00", activity_i["start_time"]) or time_compare_if_earlier_equal(activity_i["end_time"], "11:00")):
                    table_statistics.loc[0, 'Inappropriate Meal Times'] = 1
                    error_info.append("The time of lunch should be in [11:00 -- 14:00]")
                if activity_i["type"] == "dinner" and (time_compare_if_earlier_equal("20:00", activity_i["start_time"]) or time_compare_if_earlier_equal(activity_i["end_time"], "17:00")):
                    table_statistics.loc[0,  'Inappropriate Meal Times'] = 1
                    error_info.append("The time of dinner should be in [17:00 -- 20:00]")
            except:
                table_statistics.loc[0,  'Inappropriate Meal Times'] = 1
                error_info.append("Schedule of Restruants should be provided")
        

            try:
                activity_i["cost"]
                if abs(symbolic_input["people_number"] * activity_i["price"] - activity_i["cost"]) > .1:
                    table_statistics.loc[0,  'Incorrect cost Information of Restruants'] = 1
                    error_info.append("Incorrect cost information of Restruants Events [cost = price * people_number].")
            except:
                table_statistics.loc[0,  'Incorrect cost Information of Restruants'] = 1
                error_info.append("The Restruants Events should provide cost information")
            
            # 开放时间
            opentime, endtime = select_restaurant["opentime"].values[0],  select_restaurant["endtime"].values[0]
            if time_compare_if_earlier_equal(endtime, opentime):
                endtime = str(int(endtime.split(":")[0]) + 24) + ":" + endtime.split(":")[1]
            try:
                activity_i["start_time"]
                activity_i["end_time"]
                # if time_compare_if_earlier_equal(endtime, activity_i["start_time"]) or time_compare_if_earlier_equal(activity_i["end_time"], opentime): 
                if not (time_compare_if_earlier_equal(opentime, activity_i["start_time"]) and time_compare_if_earlier_equal(activity_i["end_time"], endtime)):
                    table_statistics.loc[0,  'Visiting Restruants in their closed time'] = 1
                    error_info.append("The attraction is closed now. open time: [{} -- {}]".format(opentime, endtime))
            except:
                table_statistics.loc[0,  'Visiting Restruants in their closed time'] = 1
                error_info.append("Schedule of Restruants should be provided")
            restaurants_list.append(position)
            # restaurants_time_list.append(activity_i["start_time"])

    if len(set(restaurants_list)) != len(restaurants_list):

        table_statistics.loc[0,  'Repeated Restruants Choices'] = 1
        error_info.append("Restaurants choices should not be repeated throughout the trip.")

    # print(restaurants_list)
    # print(restaurants_time_list)

    if verbose:
        if table_statistics.loc[0].sum() == 0:
            print("Restaurants passed!")
        else:
            print(error_info)
            print(table_statistics)
    return table_statistics, error_info


def Is_transport_correct(symbolic_input, plan_json, verbose=False): 
    

    target_city = symbolic_input["target_city"]
    table_statistics = pd.DataFrame(columns=['Unavailable Inner-City Transport', 'Incorrect Information of Inner-City Transporton on price, distance, and duration', 'Inccorrect cost information of Inner-City Transport'])

    error_info = []    
    try: 
        plan_json["itinerary"]
    except: 
        table_statistics.loc[0] = [1, 1, 1]
        error_info = ["Error plan type, must be python dict"]
        return table_statistics, error_info

    table_statistics.loc[0] = [0, 0, 0]

    plan = plan_json["itinerary"]
    for day_plan_i in plan:
        for activity_i in day_plan_i["activities"]:

            if "transports" in activity_i:
                
                transport_i = activity_i["transports"]

                if (len(transport_i)) == 0:
                    continue
                # print(transport_i)

                try:
                    transport_i[0]["start"]
                    transport_i[-1]["end"]
                    transport_i[0]["start_time"]
                    transport_i[-1]["end_time"]
                except:
                    table_statistics.loc[0] = [1, 1, 1]
                    error_info.append("Key Error: [start, end, start_time, end_time]")
                
                source_poi = normalize_poi_name(transport_i[0]["start"])
                target_poi = normalize_poi_name(transport_i[-1]["end"])
                start_time = transport_i[0]["start_time"]

                # print(transport_i)

                # print(source_poi, " -> ", target_poi)

                # print(GoTo(city=target_city, locationA=source_poi, locationB=target_poi, start_time=start_time, transport_type="metro", verbose=False))
                # print(GoTo(city=target_city, locationA=source_poi, locationB=target_poi, start_time=start_time, transport_type="taxi", verbose=False))
                
                if (len(transport_i)==3):
                    try:
                        tools_return = innercity_transport.goto(city=target_city, start=source_poi, end=target_poi, start_time=start_time, transport_type="metro", verbose=False)
                    except:
                        table_statistics.loc[0] = [1, 1, 1]
                        error_info.append("GoTo error city [{}], start [{}], end [{}], start_time [{}], transport_type [metro]".format(target_city, source_poi, target_poi, start_time))
                        continue


                    for idx, trans_ii in enumerate(transport_i):
                        
                        try:
                            if normalize_poi_name(trans_ii["start"]) != normalize_poi_name(tools_return[idx]["start"]):
                                table_statistics.loc[0,  'Unavailable Inner-City Transport'] = 1
                                error_info.append("Incorrect infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                        
                            if normalize_poi_name(trans_ii["end"]) != normalize_poi_name(tools_return[idx]["end"]):
                                table_statistics.loc[0,  'Unavailable Inner-City Transport'] = 1
                                error_info.append("Incorrect infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                        except:
                            table_statistics.loc[0,  'Unavailable Inner-City Transport'] = 1
                            error_info.append("Incorrect infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))

                        try:

                            if trans_ii["start_time"] != tools_return[idx]["start_time"] or trans_ii["end_time"] != tools_return[idx]["end_time"]:
                                table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                                error_info.append("Incorrect duration infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                            
                        except:
                            table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                            error_info.append("Incorrect duration infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))


                        try:

                            if abs(trans_ii["price"] - tools_return[idx]["cost"]) > 0.1:
                                table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                                error_info.append("Incorrect price infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                        except:
                            table_statistics.loc[0, 'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                            error_info.append("Incorrect price infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))

                        try:

                            if abs(trans_ii["distance"] - tools_return[idx]["distance"]) > 0.1:
                                table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                                error_info.append("Incorrect distance infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                        except:
                            table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                            error_info.append("Incorrect distance infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                        
                        if trans_ii['mode'] == 'metro':
                            try:
                                trans_ii['tickets']
                                trans_ii['cost']
                                if abs(trans_ii['price'] * trans_ii['tickets'] - trans_ii['cost']) > .1:
                                    table_statistics.loc[0,  'Incorrect cost information of Inner-City Transport'] = 1
                                    error_info.append("Incorrect cost information of transport {} -> {}".format(source_poi, target_poi) + "  [{}], [cost=price*tickets] ".format(trans_ii))
                            except:
                                table_statistics.loc[0,  'Incorrect cost information of Inner-City Transport'] = 1
                                error_info.append("Incorrect cost information of transport {} -> {}".format(source_poi, target_poi) + "  [{}], [cost=price*tickets] ".format(trans_ii))
                        elif trans_ii['mode'] == 'walk':
                            try:
                                trans_ii['cost']
                                if trans_ii['cost']!= 0:
                                    table_statistics.loc[0,  'Incorrect cost information of Inner-City Transport'] = 1
                                    error_info.append("Incorrect cost information of transport {} -> {}".format(source_poi, target_poi) + "  [{}], [cost=0] ".format(trans_ii))
                            except:
                                table_statistics.loc[0,  'Incorrect cost information of Inner-City Transport'] = 1
                                error_info.append("Incorrect cost information of transport {} -> {}".format(source_poi, target_poi) + "  [{}], [cost=0] ".format(trans_ii))

                    try:
                        if transport_i[0]["mode"] != "walk" or transport_i[2]["mode"] != "walk" or transport_i[1]["mode"] != "metro":
                            table_statistics.loc[0,  'Unavailable Inner-City Transport'] = 1
                            error_info.append("Incorrect transport type of transport {} -> {}".format(source_poi, target_poi))
                    except:
                        table_statistics.loc[0,  'Unavailable Inner-City Transport'] = 1
                        error_info.append("Incorrect transport type of transport {} -> {}".format(source_poi, target_poi))

                elif len(transport_i)==1 and transport_i[0]["mode"] in ["walk", "taxi"]:

                    try:
                        tools_return = innercity_transport.goto(city=target_city, start=source_poi, end=target_poi, start_time=start_time, transport_type=transport_i[0]["mode"], verbose=False)
                        if not isinstance(tools_return, list):
                            table_statistics.loc[0] = [1, 1, 1]
                            error_info.append("Can not find a path of transport {} -> {}".format(source_poi, target_poi))
                    except:
                        table_statistics.loc[0] = [1, 1, 1]
                        error_info.append("GoTo error city [{}], start [{}], end [{}], start_time [{}], transport_type [metro]".format(target_city, source_poi, target_poi, start_time))
                        continue
                    for idx, trans_ii in enumerate(transport_i):
                        try:
                            if normalize_poi_name(trans_ii["start"]) != normalize_poi_name(tools_return[idx]["start"]):
                                table_statistics.loc[0,  'Unavailable Inner-City Transport'] = 1
                                error_info.append("Incorrect infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                        
                            if normalize_poi_name(trans_ii["end"]) != normalize_poi_name(tools_return[idx]["end"]):
                                table_statistics.loc[0,  'Unavailable Inner-City Transport'] = 1
                                error_info.append("Incorrect infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                        except:
                            table_statistics.loc[0,  'Unavailable Inner-City Transport'] = 1
                            error_info.append("Incorrect infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))

                        try:

                            if trans_ii["start_time"] != tools_return[idx]["start_time"] or trans_ii["end_time"] != tools_return[idx]["end_time"]:
                                table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                                error_info.append("Incorrect duration infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                            
                        except:
                            table_statistics.loc[0,  'Incorrect Duration Information of Inner-City Transport'] = 1
                            error_info.append("Incorrect duration infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))


                        try:

                            if abs(trans_ii["price"] - tools_return[idx]["cost"]) > 0.1:
                                table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                                error_info.append("Incorrect price infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                        except:
                            table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                            error_info.append("Incorrect price infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))

                        try:
                            if abs(trans_ii["distance"] - tools_return[idx]["distance"]) > 0.1:
                                table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                                error_info.append("Incorrect distance infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))
                        except:
                            table_statistics.loc[0,  'Incorrect Information of Inner-City Transporton on price, distance, and duration'] = 1
                            error_info.append("Incorrect distance infomation of transport {} -> {}".format(source_poi, target_poi) + "  [{}], Tool: [{}]".format(trans_ii, tools_return[idx]))

                        if trans_ii['mode'] == 'walk':
                            try:
                                trans_ii['cost']
                                if trans_ii['cost']!= 0:
                                    table_statistics.loc[0,  'Incorrect cost information of Inner-City Transport'] = 1
                                    error_info.append("Incorrect cost information of transport {} -> {}".format(source_poi, target_poi) + "  [{}], [cost=0] ".format(trans_ii))
                            except:
                                table_statistics.loc[0,  'Incorrect cost information of Inner-City Transport'] = 1
                                error_info.append("Incorrect cost information of transport {} -> {}".format(source_poi, target_poi) + "  [{}], [cost=0] ".format(trans_ii))
                        elif trans_ii['mode'] == 'taxi':
                            try:
                                trans_ii['cost']
                                trans_ii['cars']
                                if abs(trans_ii['price'] * trans_ii['cars'] - trans_ii['cost']) > .1:
                                    table_statistics.loc[0,  'Incorrect cost information of Inner-City Transport'] = 1
                                    error_info.append("Incorrect cost information of transport {} -> {}".format(source_poi, target_poi) + "  [{}], [cost=price*cars] ".format(trans_ii))
                            except:
                                table_statistics.loc[0,  'Incorrect cost information of Inner-City Transport'] = 1
                                error_info.append("Incorrect cost information of transport {} -> {}".format(source_poi, target_poi) + "  [{}], [cost=price*cars] ".format(trans_ii))
                else:
                    table_statistics.loc[0] = [1, 1, 1]
                    error_info.append("Metro transport should be three-stages, Taxi or walk should be one-stage. {} -> {}".format(source_poi, target_poi))

                # print("passed")

    if verbose:
        if table_statistics.loc[0].sum() == 0:
            print("Innercity transport  passed!")
        else:
            print(error_info)
            print(table_statistics)
    return table_statistics, error_info

def time_compare_if_earlier_equal(time_1, time_2):

    time1 = float(time_1.split(":")[0])*60 + float(time_1.split(":")[1])
    time2 = float(time_2.split(":")[0])*60 + float(time_2.split(":")[1])
    
    
    return time1 <= time2

def time2real(time_str):
    time_str = time_str.split("次日")[-1]
    return float(time_str.split(":")[0])*60 + float(time_str.split(":")[1])

def Is_time_correct(symbolic_input, plan_json, verbose=False): 
    

        
    target_city = symbolic_input["target_city"]


    table_statistics = pd.DataFrame(columns=['Invalid duration information of each activity', 'Does not follow Chronological Order'])

    error_info = []    
    try: 
        plan_json["itinerary"]
    except: 
        table_statistics.loc[0] = [1, 1]
        error_info = ["Error plan type, must be python dict"]
        return table_statistics, error_info

    table_statistics.loc[0] = [0, 0]

    plan = plan_json["itinerary"]
    for day_plan_i in plan:
        for activity_i in day_plan_i["activities"]:
            
            # print(activity_i)
            try: activity_i["start_time"] and activity_i["end_time"]
            except: 
                table_statistics.loc[0, 'Invalid duration information of each activity'] = 1
                error_info = ["Activity should provide start_time and end_time"]
                return table_statistics, error_info
    
            activity_st_time = activity_i["start_time"]
            activity_ed_time = activity_i["end_time"]

            if time2real(activity_st_time) >= time2real(activity_ed_time) and (not activity_i["type"] in ["train", "airplane"]): # 可能出现次日到达
                table_statistics.loc[0, 'Does not follow Chronological Order'] = 1
                error_info.append("Activities must cost time: " + str(activity_i))
            

            if not "transports" in activity_i:
                continue

            if len(activity_i["transports"]) > 0:
                transport_st_time = activity_i["transports"][0]["start_time"]
                transport_ed_time = activity_i["transports"][-1]["end_time"]
            
                if time2real(activity_st_time) < time2real(transport_ed_time):

                    table_statistics.loc[0, 'Does not follow Chronological Order'] = 1
                    error_info.append("Must arrive at the location before starting the activity: " + str(activity_i))

            

    if verbose:
        if table_statistics.loc[0].sum() == 0:
            print("Time passed!")
        else:
            print(error_info)
            print(table_statistics)
    return table_statistics, error_info


def Is_space_correct(symbolic_input, plan_json, verbose=False): 

    target_city = symbolic_input["target_city"]

    table_statistics = pd.DataFrame(columns=['Invalid Transport information across positions'])

    error_info = []    
    try: 
        plan_json["itinerary"]
    except: 
        table_statistics.loc[0] = [1]
        error_info = ["Error plan type, must be python dict"]
        return table_statistics, error_info

    table_statistics.loc[0] = [0]

    plan = plan_json["itinerary"]

    position_list = []
    last_day_idx = len(plan) - 1

    for day_idx, day_plan_i in enumerate(plan):
        activities = day_plan_i["activities"]
        last_activity_idx = len(activities) - 1
        for activity_idx, activity_i in enumerate(activities):
            
            activity_type = activity_i.get("type")
            is_first_activity = day_idx == 0 and activity_idx == 0
            is_last_activity = day_idx == last_day_idx and activity_idx == last_activity_idx
            if activity_type in _INTERCITY_ACTIVITY_TYPES and not (is_first_activity or is_last_activity):
                table_statistics.loc[0, 'Invalid Transport information across positions'] = 1
                error_info.append("Intercity transport can only appear as the first or last activity: " + str(activity_i))

            if not "position" in activity_i:
                if activity_type not in _INTERCITY_ACTIVITY_TYPES:
                    table_statistics.loc[0, 'Invalid Transport information across positions'] = 1
                    error_info.append("Only intercity transport may omit position: " + str(activity_i))
                    continue
                if "start" in activity_i and "end" in activity_i:
                    current_position = normalize_poi_name(activity_i["start"])
                else:
                    table_statistics.loc[0, 'Invalid Transport information across positions'] = 1
                    error_info.append("Every activity need a position or start/end keys: " + str(activity_i))
                    continue

            else:
                current_position = normalize_poi_name(activity_i["position"])

            if not "transports" in activity_i:
                # print(activity_i)
                table_statistics.loc[0, 'Invalid Transport information across positions'] = 1
                error_info.append("Need trasnports: ".format(activity_i))

            # try: activity_i["position"] and activity_i["transports"]
            # except: return False

            position_i = current_position

            if (len(position_list) > 0) and position_i != position_list[-1]:

                if not "transports" in activity_i:
                    table_statistics.loc[0, 'Invalid Transport information across positions'] = 1
                    error_info.append("There must be transport between activities in different possitions: " + str(activity_i))
                    # continue

                elif (len(activity_i["transports"]) < 1):

                    table_statistics.loc[0, 'Invalid Transport information across positions'] = 1
                    error_info.append("There must be transport between activities in different possitions: " + str(activity_i))
                    # continue

                else:
                    if normalize_poi_name(activity_i["transports"][0]["start"]) != position_list[-1]:

                        table_statistics.loc[0, 'Invalid Transport information across positions'] = 1
                        error_info.append("The origin of the transport must be equal to the position of the previous activity.: " + str(activity_i))
                        # continue

                    if normalize_poi_name(activity_i["transports"][-1]["end"]) != position_i:

                        table_statistics.loc[0, 'Invalid Transport information across positions'] = 1
                        error_info.append("The destination of the transport must be equal to the position of the current activity.: " + str(activity_i))
                        # continue

            if "position" in activity_i:
                position_list.append(normalize_poi_name(activity_i["position"]))
            else:
                position_list.append(normalize_poi_name(activity_i["end"]))

    # print("position_list: ", position_list)

    if verbose:
        if table_statistics.loc[0].sum() == 0:
            print("Space passed!")
        else:
            print(error_info)
            print(table_statistics)
    return table_statistics, error_info


def func_commonsense_constraints(symbolic_input, plan_json, verbose=False, lang=None):
    _set_tool_lang(lang or _infer_lang(symbolic_input))

    func_list = [Is_activity_grounded, Is_intercity_transport_correct, Is_attractions_correct, Is_hotels_correct, Is_restaurants_correct, Is_transport_correct, Is_time_correct, Is_space_correct]
    succ_flag = True
    error_list = []
    for func in func_list:
        table_res, error_info = func(symbolic_input, plan_json, verbose=verbose)

        if table_res.iloc[0].sum() > 0:
            succ_flag = False
        error_list.append(error_info)

        # except Exception:

        #     print(Exception)

    if not succ_flag:
        print("Commonsense constraints failed!")
        for err_info in error_list:
            print(err_info)

    return succ_flag            


def evaluate_commonsense_constraints(data_index, symbolic_input_dict, plan_json_dict, verbose=False):
    # assert len(symbolic_input_list)==len(plan_json_list)

    func_list = [Is_activity_grounded, Is_intercity_transport_correct, Is_attractions_correct, Is_hotels_correct, Is_restaurants_correct, Is_transport_correct, Is_time_correct, Is_space_correct]
    total_correct = 0

    individual_results = []
    results_per_sample=[]


    result_agg = pd.DataFrame(columns=['data_id'])
    result_agg['data_id'] = data_index

    individual_succ = 0

    for ii, idx in tqdm(enumerate(data_index), total=len(data_index)):
    # for i,(symbolic_input,plan_json) in enumerate(zip(symbolic_input_list,plan_json_list)):
        


        symbolic_input, plan_json = symbolic_input_dict[idx], plan_json_dict[idx]  
        
        if verbose:
            print(symbolic_input)
            print(plan_json)
        
        for func in func_list:

            table_res, error_info = func(symbolic_input, plan_json, verbose=verbose)
            for colum_i in table_res.columns:
                if colum_i not in result_agg.columns:
                    result_agg[colum_i] = 0

                result_agg.loc[ii, colum_i] = table_res[colum_i].loc[0]

            # print(info)
        if result_agg.loc[ii][1:].sum() == 0:
            individual_succ += 1
                            

    total_count=len(data_index)
    micro_accuracy = 1. - result_agg.drop("data_id", axis=1).sum().sum() / (total_count * (result_agg.shape[1] - 1))
    
    macro_accuracy = individual_succ / total_count

    return macro_accuracy*100, micro_accuracy*100, result_agg

if __name__ == "__main__":
    
    
    
    # test_example=load_json_file("./example/query_53.json")
    # test_plan=load_json_file("./example/plan_53.json")
    # evaluate_commonsense_constraints([test_example], [test_plan])
    
    # exit(0)
    
    symbolic_input_list=[]
    plan_json_list=[]

    for i in range(1):
        test_plan_path='./example/a_result.json'.format(i+1)
        test_example_path='./example/a_query.json'.format(i+1)
        test_example=load_json_file(test_example_path)
        test_plan=load_json_file(test_plan_path)
        symbolic_input_list.append(test_example)
        plan_json_list.append(test_plan)
    macro_accuracy, micro_accuracy, _ =evaluate_commonsense_constraints(symbolic_input_list,plan_json_list)
    print('macro: {}%, micro: {}%'.format(macro_accuracy,micro_accuracy))

    # test_plan_path='./example/plan_4.json'
    # test_example_path='./example/query_4.json'
    # test_example=load_json_file(test_example_path)
    # test_plan=load_json_file(test_plan_path)

    # print(Is_intercity_transport_correct(test_example,test_plan))
    # print(Is_attractions_correct(test_example,test_plan))
    # print(Is_hotels_correct(test_example,test_plan))
    # print(Is_restaurants_correct(test_example,test_plan))
    # print(Is_transport_correct(test_example,test_plan))
    # print(Is_time_correct(test_example,test_plan))
    # print(Is_space_correct(test_example,test_plan))

    
    # pass_flag = True

    

    # info_list = []
    # for func_i in func_list:
    #     flag, info = func_i(test_example,test_plan)

    #     print(info)

    #     pass_flag = pass_flag and flag
    #     info_list.append(info)

    # print("final result: ", pass_flag)
    
    # for item in info_list:
    #     print(item)
    # print(info_list)
