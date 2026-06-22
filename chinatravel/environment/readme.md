# APIs

## WorldEnv

The `WorldEnv` class is a wrapper of the APIs. You can use it by instancing `WorldEnv` class and call the APIs with the command string. The command string is parsed as a restricted function-call expression: only registered API names, literal arguments, keyword arguments, and simple one-argument lambda predicates are accepted. All POI names should be exactly the same as the data in the sandbox.

For example:

```python
env = WorldEnv()
cmd_str = "attractions_keys('上海')"
print(env(cmd_str))
```

The output is:

```cmd
[('id', <class 'numpy.int64'>), ('name', <class 'str'>), ('type', <class 'str'>), ('lat', <class 'numpy.float64'>), ('lon', <class 'numpy.float64'>), ('opentime', <class 'str'>), ('endtime', <class 'str'>), ('price', <class 'numpy.float64'>), ('recommendmintime', <class 'numpy.float64'>), ('recommendmaxtime', <class 'numpy.float64'>)]
```

The return value of APIs is an `EnvOutput` object, original results can be accessed by `o["data"]`, if `o` is the `EnvOutput` object.

We also implement `__str__` method for `EnvOutput` to ensure the string won't be too long when input to the LLM. And we also offer `next_page` API in `WorldEnv` to get the next page of the last query result.

**APIs in `WorldEnv`:**

- attractions_keys(city: str)

  - Description: Returns a list of (key, type) pairs of the attractions data.
  - Parameters:
    - city: The city name.
  - Example: `env("attractions_keys('上海')")`
- attractions_select(city: str, key: str, func: Callable):

  - Description: Returns a DataFrame with data filtered by the specified key with the specified function.
  - Parameters:
    - city: The city name.
    - key: The key column to filter, only one key can be used.
    - func: The function applied to the key column, must return a boolean value. Only apply to one key.
  - Example: `env("attractions_select('上海', 'type', lambda x: x == '公园')")`
- attractions_id_is_open(city: str, id: int, time: str):

  - Description: Returns whether the attraction with the specified ID is open at the specified time.
  - Parameters:
    - city: The city name.
    - id: The ID of the attraction.
    - time: The time to check, in the format 'HH:MM'.
  - Example: `env("attractions_id_is_open('上海', 1, '08:00')")`
- attractions_nearby(city: str, point: str, topk: int, dist: float):

  - Description: Returns the top K attractions within the specified distance of the location.
  - Parameters:
    - city: The city name.
    - point: The name of the location.
    - topk: The number of attractions to return.
    - dist: The maximum distance from the location, default is 2.
  - Example: `env("attractions_nearby('上海', '上海迪士尼度假区', 5, 5)")`
- attractions_types(city: str):

  - Description: Returns a list of unique attraction types.
  - Parameters:
    - city: The city name.
- accommodations_keys(city: str):

  - Description: Returns a list of (key, type) pairs of the accommodations data.
  - Parameters:
    - city: The city name.
- accommodations_select(city: str, key: str, func: Callable):

  - Description: Returns a DataFrame with data filtered by the specified key with the specified function.
  - Parameters:
    - city: The city name.
    - key: The key column to filter, only one key can be used.
    - func: The function applied to the key column, must return a boolean value. Only apply to one key.
  - Example: `env("accommodations_select('上海', 'name', lambda x: x == '桔子水晶上海外滩豫园酒店')")`
- accommodations_nearby(city: str, point: str, topk: int, dist: float):

  - Description: Returns the top K accommodations within the specified distance of the location.
  - Parameters:
    - city: The city name.
    - point: The name of the location.
    - topk: The number of accommodations to return.
    - dist: The maximum distance from the location, default is 5.
- restaurants_keys(city: str):

  - Description: Returns a list of (key, type) pairs of the restaurants data.
  - Parameters:
    - city: The city name.
  - Example: `env("restaurants_keys('上海')")`
- restaurants_select(city: str, key: str, func: Callable):

  - Description: Returns a DataFrame with data filtered by the specified key with the specified function.
  - Parameters:
    - city: The city name.
    - key: The key column to filter, only one key can be used.
    - func: The function applied to the key column, must return a boolean value. Only apply to one key.
  - Example: `env("restaurants_select('上海', 'cuisine', lambda x: x == '川菜')")`
- restaurants_id_is_open(city: str, id: int, time: str):

  - Description: Returns whether the restaurant with the specified ID is open at the specified time and day.
  - Parameters:
    - city: The city name.
    - id: The ID of the restaurant.
    - time: The time to check, in the format 'HH:MM'.
  - Example: `env("restaurants_id_is_open('上海', 1, '08:00')")`
- restaurants_nearby(city: str, point: str, topk: int, dist: float):

  - Description: Returns the top K restaurants within the specified distance of the location.
  - Parameters:
    - city: The city name.
    - point: The name of the location.
    - topk: The number of restaurants to return.
    - dist: The maximum distance from the location, default is 2.
  - Example: `env("restaurants_nearby('上海', '南兴园', 5, 5)")`
- restaurants_with_recommended_food(city: str, food: str):

  - Description: Returns all restaurants with the specified food in their recommended dishes.
  - Parameters:
    - city: The city name.
    - food: The food to search for.
  - Example: `env("restaurants_with_recommended_food('上海', '红烧肉')")`
- restaurants_cuisine(city: str):

  - Description: Returns a list of unique restaurant cuisines.
  - Parameters:
    - city: The city name.
  - Example: `env("restaurants_cuisine('上海')")`
- goto(city: str, start: str, end: str, start_time: str, transport_type: str):

  - Description: Returns a list of transportation options between two locations.
  - Parameters:
    - city: The city name.
    - start: The start point's name. Must be a location name and match the data exactly.
    - end: The end point's name. Must be a location name and match the data exactly.
    - start_time: The departure time in the format 'HH:MM'.
    - transport_type: The mode of transportation, must in ['walk', 'taxi', 'metro'].
  - Example: `env('''goto(''上海'', ''上海迪士尼度假区'', ''南兴园'', ''18:00'', ''taxi'')''')`
- intercity_transport_select(start_city: str, end_city: str, intercity_type: str, earliest_leave_time: str = "00:00"):

  - Description: get the intercity transportation information between two cities. You need to call this function at least twice to get the transportation information between two locations for going and returning.
  - Parameters:
    - start_city: The start city name.
    - end_city: The end city name.
    - intercity_type: The type of intercity transportation, must in ['train', 'airplane'].
    - earliest_leave_time: The earliest leave time in the format 'HH:MM'.
  - Example: `env("intercity_transport_select('上海', '北京', 'train', '08:00')")`
- next_page() # Note that this is a special API for `WorldEnv` class.

  - Description: Get the next page of last query result.
  - Parameters: None.
  - Example: `env("next_page()")`

## APIs

We also provide orginal APIs for you to use. Import only the tool classes you need.

For example:

```python
from chinatravel.environment.tools import Attractions

attraction = Attractions()
print(attraction.keys("上海"))
```

The APIs are listed below:

- `Attractions`
  - `keys(city: str)`
    - Returns a list of (key, type) pairs of the attractions data.
    - Example: `attraction.keys("上海")`
  - `select(city: str, key: str, func: Callable)`
    - Returns a DataFrame with data filtered by the specified key with the specified function.
    - Example: `attraction.select("上海", "type", lambda x: x == "公园")`
  - `id_is_open(city: str, id: int, time: str)`
    - Returns whether the attraction with the specified ID is open at the specified time.
    - Example: `attraction.id_is_open("上海", 1, "08:00")`
  - `nearby(city: str, point: str, topk: int, dist: float)`
    - Returns the top K attractions within the specified distance of the location.
    - Example: `attraction.nearby("上海", "上海迪士尼度假区", 5, 5)`
  - `get_type_list(city: str)`
    - Returns a list of unique attraction types.
    - Example: `attraction.get_type_list("上海")`
- `Accommodations`
  - `keys(city: str)`
    - Returns a list of (key, type) pairs of the accommodations data.
    - Example: `accommodation.keys("上海")`
  - `select(city: str, key: str, func: Callable)`
    - Returns a DataFrame with data filtered by the specified key with the specified function.
    - Example: `accommodation.select("上海", "name", lambda x: x == "桔子水晶上海外滩豫园酒店")`
  - `nearby(city: str, point: str, topk: int, dist: float)`
    - Returns the top K accommodations within the specified distance of the location.
    - Example: `accommodation.nearby("上海", "上海迪士尼度假区", 5, 5)`
- `Restaurants`
  - `keys(city: str)`
    - Returns a list of (key, type) pairs of the restaurants data.
    - Example: `restaurant.keys("上海")`
  - `select(city: str, key: str, func: Callable)`
    - Returns a DataFrame with data filtered by the specified key with the specified function.
    - Example: `restaurant.select("上海", "cuisine", lambda x: x == "川菜")`
  - `id_is_open(city: str, id: int, time: str)`
    - Returns whether the restaurant with the specified ID is open at the specified time and day.
    - Example: `restaurant.id_is_open("上海", 1, "08:00")`
  - `nearby(city: str, point: str, topk: int, dist: float)`
    - Returns the top K restaurants within the specified distance of the location.
    - Example: `restaurant.nearby("上海", "南兴园", 5, 5)`
  - `restaurants_with_recommended_food(city: str, food: str)`
    - Returns all restaurants with the specified food in their recommended dishes.
    - Example: `restaurant.restaurants_with_recommended_food("上海", "红烧肉")`
  - `get_cuisine_list(city: str)`
    - Returns a list of unique restaurant cuisines.
    - Example: `restaurant.get_cuisine_list("上海")`
- `IntercityTransport`
  - `select(start_city: str, end_city: str, intercity_type: str, earliest_leave_time: str = "00:00")`
    - Returns the intercity transportation information between two cities. You need to call this function at least twice to get the transportation information between two locations for going and returning.
- `Transportation`
  - `goto(city: str, start: str, end: str, start_time: str, transport_type: str)`
    - Returns a list of transportation options between two locations.
    - Example: `transportation.goto("上海", "上海迪士尼度假区", "南兴园", "18:00", "taxi")`
- `Poi`
  - `search(self, city: str, name: str)`
    - Returns the POI's coordinate with the specified name in the specified city.
    - Example: `poi.search("上海", "上海迪士尼度假区")`
