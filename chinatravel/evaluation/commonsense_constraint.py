
import sys

# from chinatravel.environment.tools.accommodations.apis import Accommodations
# from chinatravel.environment.tools.restaurants.apis import Restaurants
# from chinatravel.environment.tools.attractions.apis import Attractions
# from chinatravel.environment.tools.intercity_transport.apis import IntercityTransport
# from chinatravel.environment.tools.transportation.apis import Transportation
# from env.tools.transportation.apis import GoTo
# from envs import goto
import json
import os
import sys
from tqdm import tqdm

    
import pandas as pd

# accommodation = Accommodations()
# restaurants = Restaurants()
# attractions = Attractions()
# intercity_transport=IntercityTransport()
# innercity_transport=Transportation()

from chinatravel.symbol_verification.commonsense_constraint import (
    Is_activity_grounded,
    Is_intercity_transport_correct,
    Is_attractions_correct,
    Is_hotels_correct,
    Is_restaurants_correct,
    Is_transport_correct,
    Is_time_correct,
    Is_space_correct,
    _infer_lang,
    _set_tool_lang,
)

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



def evaluate_commonsense_constraints(data_index, symbolic_input_dict, plan_json_dict, verbose=False, lang=None):
    # assert len(symbolic_input_list)==len(plan_json_list)

    func_list = [Is_activity_grounded, Is_intercity_transport_correct, Is_attractions_correct, Is_hotels_correct, Is_restaurants_correct, Is_transport_correct, Is_time_correct, Is_space_correct]
    total_correct = 0

    individual_results = []
    results_per_sample=[]


    result_agg = pd.DataFrame(columns=['data_id'])
    result_agg['data_id'] = data_index

    individual_succ = 0
    pass_id = []

    for ii, idx in tqdm(enumerate(data_index), total=len(data_index)):
    # for i,(symbolic_input,plan_json) in enumerate(zip(symbolic_input_list,plan_json_list)):
        


        symbolic_input, plan_json = symbolic_input_dict[idx], plan_json_dict[idx]
        _set_tool_lang(lang or _infer_lang(symbolic_input))
        
        if verbose:
            print(symbolic_input)
            print(plan_json)
        try:
            for func in func_list:

                table_res, error_info = func(symbolic_input, plan_json, verbose=verbose)
                
                if verbose:
                    print(error_info)
                
                for colum_i in table_res.columns:
                    if colum_i not in result_agg.columns:
                        result_agg[colum_i] = 0

                    result_agg.loc[ii, colum_i] = table_res[colum_i].loc[0]

                # print(info)
            if result_agg.loc[ii][1:].sum() == 0:
                individual_succ += 1
                pass_id.append(idx)
        except Exception as message:
            pass
            # print("Error: ", message)
            # print(symbolic_input)
            # print(plan_json)
        
                            

    total_count=len(data_index)
    micro_accuracy = 1. - result_agg.drop("data_id", axis=1).sum().sum() / (total_count * (result_agg.shape[1] - 1))
    
    macro_accuracy = individual_succ / total_count

    return macro_accuracy*100, micro_accuracy*100, result_agg, pass_id

if __name__ == "__main__":
    
    
    
    from evaluation.utils import load_json_file
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
