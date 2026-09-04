import ast

from fuzzywuzzy import process as fuzzy_process

from chinatravel.environment.tools import Poi


class FunctionValueTracker(ast.NodeVisitor):
    """
    静态分析工具，用于追踪指定函数的调用值并验证最终比较是否合法。
    需要注意的是本工具使用了很多理想化的假设，包括但不限于：
    - 代码中的变量名不会被重复定义或覆盖
    - 添加到可迭代对象的元素不会被修改或删除
    - 可迭代对象为List或Set且使用append或add方法添加元素
    - 比较操作数为常量值、列表或集合
    - 没有进行特殊比较的Bool函数
    - ...
    """

    def __init__(self, target_func, valid_values):
        self.target_func = target_func  # 要追踪的目标函数名
        self.valid_values = set(valid_values)  # 允许的合法值集合
        self.comparisons = []  # 保存比较情况
        self.errors = []  # 保存不合法的比较
        self.usage_paths = []  # 保存函数返回值的使用场景
        self.assignments = {}  # 保存赋值记录

    def reset(self):
        """
        重置分析器状态。
        """
        self.comparisons = []
        self.errors = []
        self.usage_paths = []
        self.assignments = {}

    def visit_Assign(self, node):
        """
        检查目标函数的返回值是否被赋值给变量。
        """
        # 如果赋值的值的id位于assignments中
        if isinstance(node.value, ast.Name) and node.value.id in self.assignments:
            # 添加到assignments中
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.assignments[target.id] = ast.unparse(node)
        # 如果赋值的值是目标函数的返回值
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == self.target_func
        ):
            # 将目标函数的返回值赋给目标变量
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.assignments[target.id] = ast.unparse(node)

        self.generic_visit(node)

    def visit_Compare(self, node):
        """
        检查目标函数返回值或变量是否参与比较，无论是在左侧还是右侧。
        """
        compared_values = set()
        involved = False
        check_pos = ""
        # 检查左侧操作数
        if isinstance(node.left, ast.Call) and node.left.func.id == self.target_func:
            involved = True
            check_pos = "right"
        elif isinstance(node.left, ast.Name) and node.left.id in self.assignments:
            involved = True
            check_pos = "right"

        # 检查右侧操作数
        for comparator in node.comparators:
            if (
                isinstance(comparator, ast.Call)
                and isinstance(comparator.func, ast.Name)
                and comparator.func.id == self.target_func
            ):
                involved = True
                check_pos = "left"
            elif isinstance(comparator, ast.Name) and comparator.id in self.assignments:
                involved = True
                check_pos = "left"

        # 如果目标函数的返回值参与了比较，则处理
        if involved:
            if check_pos == "left":
                compared_values = self._extract_compared_values([node.left])
            elif check_pos == "right":
                compared_values = self._extract_compared_values(node.comparators)
            # 保存比较记录
            self.comparisons.append(
                {"code": ast.unparse(node), "compared_values": compared_values}
            )
            # 检查合法性
            if not compared_values.issubset(self.valid_values):
                self.errors.append(
                    {
                        "code": ast.unparse(node),
                        "invalid_values": compared_values - self.valid_values,
                    }
                )

        self.generic_visit(node)

    def visit_Call(self, node):
        """
        检查目标函数返回值的使用场景，包括直接调用、赋值给变量、传递给方法（如 append、add）。
        """
        # 检查是否直接调用目标函数
        if isinstance(node.func, ast.Name) and node.func.id == self.target_func:
            self.usage_paths.append(
                {
                    "type": "function_call",
                    "code": ast.unparse(node),
                }
            )

        # 检查方法调用，如 append 和 add
        if isinstance(node.func, ast.Attribute):
            method_target = node.func.value  # 方法调用的目标对象

            # 检查列表的 append 方法
            if (
                node.func.attr == "append"
                and isinstance(method_target, ast.Name)
                and node.args
            ):
                # 检查参数是否是目标函数的调用或跟踪的变量
                if (
                    isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == self.target_func
                ) or (
                    isinstance(node.args[0], ast.Name)
                    and node.args[0].id in self.assignments
                ):
                    self.usage_paths.append(
                        {
                            "type": "list_append",
                            "list": method_target.id,
                            "value": ast.unparse(node.args[0]),
                            "code": ast.unparse(node),
                        }
                    )
                    self.assignments[method_target.id] = ast.unparse(node)

            # 检查集合的 add 方法
            elif (
                node.func.attr == "add"
                and isinstance(method_target, ast.Name)
                and node.args
            ):
                # 检查参数是否是目标函数的调用或跟踪的变量
                if (
                    isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == self.target_func
                ) or (
                    isinstance(node.args[0], ast.Name)
                    and node.args[0].id in self.assignments
                ):
                    self.usage_paths.append(
                        {
                            "type": "set_add",
                            "set": method_target.id,
                            "value": ast.unparse(node.args[0]),
                            "code": ast.unparse(node),
                        }
                    )
                    self.assignments[method_target.id] = ast.unparse(node)

        self.generic_visit(node)

    def _extract_compared_values(self, comparators):
        """
        从比较操作数中提取常量值，支持列表、集合和单一值。
        """
        compared_values = set()
        for comparator in comparators:
            if isinstance(comparator, ast.List):  # 列表比较
                compared_values.update(
                    elt.value
                    for elt in comparator.elts
                    if isinstance(elt, ast.Constant)
                )
            elif isinstance(comparator, ast.Set):  # 集合比较
                compared_values.update(
                    elt.value
                    for elt in comparator.elts
                    if isinstance(elt, ast.Constant)
                )
            elif isinstance(comparator, ast.Constant):  # 单一值比较
                compared_values.add(comparator.value)
        return compared_values


class CodeBlockChecker:
    def __init__(self, func_name_list, valid_values_list, need_fuzzy_list):
        assert len(func_name_list) == len(valid_values_list)
        self.func_name_list = func_name_list
        self.valid_values_list = valid_values_list
        self.need_fuzzy_list = need_fuzzy_list
        self.trackers = {}
        for i in range(len(func_name_list)):
            self.trackers[func_name_list[i]] = FunctionValueTracker(
                func_name_list[i], valid_values_list[i]
            )

    def reset(self):
        for tracker in self.trackers.values():
            tracker.reset()

    def check(self, code):
        tree = ast.parse(code)
        error_info = []
        for func_name, tracker in self.trackers.items():
            tracker.reset()
            tracker.visit(tree)
            for error in tracker.errors:
                error_code = error["code"]
                invalid_values = error["invalid_values"]
                error_info_str = f"invalid compare value in code: {error_code}, the invalid values compared with func {tracker.target_func}'s return value: {invalid_values}. Either change the func or the compare values."
                if func_name in self.need_fuzzy_list:
                    valid_values = tracker.valid_values
                    valid_values_list = list(valid_values)
                    for invalid_value in invalid_values:
                        fuzzy_result = fuzzy_process.extract(
                            invalid_value,
                            valid_values_list,
                            limit=len(valid_values_list),
                        )
                        best_score = fuzzy_result[0][1]
                        res_fuzzy_result = []
                        for result in fuzzy_result:
                            if result[1] == best_score or len(res_fuzzy_result) < 10:
                                res_fuzzy_result.append(result[0])
                        error_info_str += f"For invalid value: {invalid_value}, the most similar valid values are: {res_fuzzy_result}"
                error_info.append(error_info_str)
        return error_info, {
            func_name: tracker.errors for func_name, tracker in self.trackers.items()
        }


class HardLogicPyChecker(CodeBlockChecker):
    _poi = Poi(lang="en")

    def __init__(self, target_city):
        func_name_list = [
            "activity_type",
            "attraction_type",
            "restaurant_type",
            "accommodation_type",
            "innercity_transport_type",
            "room_type",
            "intercity_transport_type",
            "activity_position",
        ]
        valid_values_list = [
            [
                "attraction",
                "breakfast",
                "lunch",
                "dinner",
                "accommodation",
                "train",
                "airplane",
            ],
            ['Museum/Memorial Hall', 'Art museum', 'Red tourism sites', 'natural scenery', 'Cultural Landscape', 'University campus', 'historical site', 'Amusement Park/Sports Entertainment', 'Garden', 'Other', 'Cultural Tourism Area', 'park', 'commercial district'],
            ['Yunnan cuisine', 'Tibetan cuisine', 'Northeastern Chinese cuisine', 'Barbecue', 'Asian cuisine', 'Cantonese cuisine', 'Northwestern Chinese cuisine', 'Fujian cuisine', 'Hakka cuisine', 'Fast food and casual dining', 'Sichuan cuisine', 'Taiwanese cuisine', 'Other', 'Halal cuisine', 'Snacks', 'Western cuisine', 'Vegetarian cuisine', 'Japanese cuisine', 'Jiangsu-Zhejiang cuisine', 'Hubei cuisine', 'Southeast Asian cuisine', 'Hunan cuisine', 'Beijing cuisine', 'Korean cuisine', 'Seafood', 'Middle Eastern cuisine', 'fusion cuisine', 'Teahouse', 'Bar/Pub', 'Creative Cuisine', 'buffet', 'coffee shop', 'Shanghai cuisine', 'Huizhou cuisine', 'Latin American cuisine', 'Shandong Cuisine', 'Xinjiang cuisine', 'Farmhouse cuisine', 'Hainan cuisine', 'Hot pot', 'Bakery and Desserts', 'Other Chinese Cuisine'],
            ["Kids' Club", 'Air purifier', 'Mountain View Room', 'Private Hot Spring Room', 'Courtyard house', 'hot spring', 'Lakeside Residence', 'e-sports hotel', 'Hot spring bathing', 'Executive Lounge', 'Charging station', 'Designer hotel', 'homestay', 'Lake View Room', 'Stunning Night Views', 'Luggage Storage', 'Chinese-style courtyard', 'Billiards Room', 'Private Pool', 'Fishing', 'Charming sea view', 'Garden Architecture', 'Old Western-style house', "Children's Pool", 'Historic Residence', 'Mahjong and Card Game Room', 'Smart Room Control', "Couple's Room", 'small and beautiful', 'Tea Room', 'Family-themed room', 'Multifunction Hall', 'Laundry room', 'inn', 'Self-operated family room', 'Parking lot', 'Recommended by the Boss', 'River view room', 'Sunbathing area', 'Self-operated entertainment room', 'Kitchen', 'Air conditioning', 'Instagrammable pool', 'Villa', 'Free parking', 'Laundry service', 'Great view from the window', 'Serviced Apartment', 'Conference Hall', 'Family Room', '24-hour front desk', 'Business Center', 'Early Park Entry', 'Farm stay', 'Smart toilet', 'Gourmet Hotel', 'Spa', 'Photogenic', 'Ocean View Room', 'Swimming Pool', 'Media Room', 'Butler Service', 'Airport shuttle service', 'Sauna', 'Robot Service', "Children's Playground", 'Fitness Room', 'Washing machine', 'Self-operated Comfort Sleep Room', 'Pet-friendly', 'e-sports room', 'Excellent location', 'Suite'],
            ["metro", "taxi", "walk"],
            [1, 2],
            ["train", "airplane"],
        ]
        city_key = target_city
        if city_key not in self._poi.data and isinstance(city_key, str):
            city_key = city_key.capitalize()
        valid_values_list.append(list(self._poi.data[city_key].keys()))
        need_fuzzy_list = ["activity_position"]
        super().__init__(func_name_list, valid_values_list, need_fuzzy_list)


def test_data():
    import os
    from tqdm import tqdm

    project_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir)
    )
    from chinatravel.data.load_datasets import load_json_file

    query_list = []
    data_folder = os.path.join(project_path, "chinatravel/data")
    for root, dirs, files in os.walk(data_folder):
        for file in files:
            if file.endswith(".json"):
                file_path = os.path.join(root, file)
                if "ood" in file_path:
                    continue
                query = load_json_file(file_path)
                uid = file.split(".json")[0]
                query_list.append(query)

    error_uid_list = []
    for query in tqdm(query_list):
        error_info_list = []
        if "hard_logic_py" not in query:
            print(f"!!!uid: {uid}")
        checker = HardLogicPyChecker(query["target_city"])
        codes = query["hard_logic_py"]
        for code in codes:
            error_info, _ = checker.check(code)
            error_info_list.extend(error_info)
        if len(error_info_list) > 0:
            # print(f"uid: {query['uid']}")
            # # print(f"query: {query}")
            # print(f"error_info: {error_info_list}")
            # break
            error_uid_list.append(query["uid"])
    print(f"error_uid_list: {error_uid_list}")
