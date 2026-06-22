from chinatravel.symbol_verification.concept_func import func_dict
from chinatravel.symbol_verification.dsl import execute_dsl_code
from copy import deepcopy

def collect_personal_error(problem, plan, verbose=False):
    
    if not 'hard_logic_nl' in problem:
        print(f"Data id {problem['uid']}, no hard_logic_nl information.")
        return []
    if len(problem["hard_logic_py"]) != len(problem["hard_logic_nl"]):
        print(f"Data id {problem['uid']}, hard_logic_py and hard_logic_nl are not consistent.")
        return []

    error_info = []
    for idx, constraint in enumerate(problem["hard_logic_py"]):
        vars_dict = deepcopy(func_dict)
        vars_dict["plan"] = plan
        try:
            execute_dsl_code(constraint, vars_dict, allowed_builtins={"set": set})
            res_i = vars_dict.get("result", False)
            if not res_i:
                error_info.append(f"用户要求未被满足：{problem['hard_logic_nl'][idx]}")
        except Exception as e:
            if verbose:
                print(f"Error evaluating constraint '{constraint}': {e}")
            error_info.append(f"Raise Error when evaluating constraint {problem['hard_logic_nl'][idx]}")
        # print(results)
    return error_info
