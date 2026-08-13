from chinatravel.symbol_verification.concept_func import func_dict
from chinatravel.symbol_verification.dsl import execute_dsl_code
from copy import deepcopy


def evaluate_preference_py(preference_list, plan, verbose=False):


    # time_cost = 0
    # transport_count = 0
    # for activity in allactivities(plan):
    #     transports = activity_transports(activity)
    #     if transports!=[]:
    #         transport_count += 1
    #         time_cost += innercity_transport_time(transports)
    # average_time_cost = time_cost / transport_count if transport_count > 0 else -1

    # print(average_time_cost)

    
    # target_poi = '大足石刻'
    # poi_list = list()
    # total_distance = 0
    # poi_count = 0
    # city = target_city(plan)
    # for activity in allactivities(plan):
    #     if activity_type(activity) in ['breakfast', 'lunch', 'dinner', 'accommodation', 'attraction']:
    #         poi_list.append(activity_position(activity))
    # for poi in poi_list:
    #     total_distance += poi_distance(city, target_poi, poi)
    #     poi_count += 1
    # average_dist_cost = total_distance / poi_count if poi_count > 0 else -1
    # print(average_dist_cost)

    results = []
    # hard_logic_py.append(debug_logic_py)
    for _, preference_concept, preference_code in preference_list:
        preference_code = normalize_concept_constraint_source(preference_code)
        vars_dict = deepcopy(func_dict)
        vars_dict["plan"] = plan
        try:
            execute_dsl_code(
                preference_code,
                vars_dict,
                allowed_builtins={"set": set, "list": list},
            )
            res_i = vars_dict.get(preference_concept, None)
            results.append(float(res_i))
        except Exception as e:
            if verbose:
                print(f"Error evaluating preference '{preference_code}': {e}")
            results.append(None)
        # print(results)
    return results
