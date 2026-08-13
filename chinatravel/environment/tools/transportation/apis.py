import os
import json
import heapq
from geopy.distance import geodesic
from geographiclib.geodesic import Geodesic

from chinatravel.environment.tools.poi.apis import Poi
from chinatravel.environment.language import CITY_SLUGS, city_names, normalize_lang, relative_database_path


def get_lines_and_stations(city, SUBWAY_PATH):
    stations_all = []
    metro_lines = {}
    with open(SUBWAY_PATH, "r", encoding="utf-8") as file:
        subway_data = json.load(file)
    for line in subway_data[city]:
        metro_lines[line["name"]] = []
        for station in line["stations"]:
            lat, lon = map(float, station["position"].split(","))
            metro_lines[line["name"]].append(station["name"])
            stations_all.append({"name": station["name"], "position": (lon, lat)})
    station_to_line = {}
    for line, stations in metro_lines.items():
        for station in stations:
            station_to_line[station] = line
    return stations_all, metro_lines, station_to_line


def build_graph(metro_lines):
    graph = {}
    for line, stations in metro_lines.items():
        for i in range(len(stations)):
            if stations[i] not in graph:
                graph[stations[i]] = []
            if i > 0:
                graph[stations[i]].append(stations[i - 1])
            if i < len(stations) - 1:
                graph[stations[i]].append(stations[i + 1])
    return graph


def get_line_change(station_to_line, path):
    line_changes = []

    for station in path:
        if station in station_to_line:
            line_changes.append(station_to_line[station])


def add_time(time1, hours):

    hour, minu = int(time1.split(":")[0]), int(time1.split(":")[1])

    time_delta = int(hours * 60)
    min_new = minu + time_delta

    if min_new >= 60:
        hour_new = hour + int(min_new / 60)
        min_new = min_new % 60
    else:
        hour_new = hour

    if hour_new < 10:
        time_new = "0" + str(hour_new) + ":"
    else:
        time_new = str(hour_new) + ":"
    if min_new < 10:

        time_new = time_new + "0" + str(min_new)
    else:
        time_new = time_new + str(min_new)

    return time_new


def dijkstra(graph, start, end):
    queue = [(0, start, [])]
    seen = set()
    while queue:
        (cost, node, path) = heapq.heappop(queue)
        if node in seen:
            continue
        path = path + [node]
        seen.add(node)
        if node == end:
            return path
        for next_node in graph.get(node, []):
            if next_node not in seen:
                heapq.heappush(queue, (cost + 1, next_node, path))
    return []


def find_shortest_path(graph, start, end):
    return dijkstra(graph, start, end)


def find_nearest_station(location, stations):
    nearest_station = None
    min_distance = float("inf")
    latitude, longitude = location
    inverse = Geodesic.WGS84.Inverse
    for station in stations:
        station_latitude, station_longitude = station["position"]
        distance = (
            inverse(
                latitude,
                longitude,
                station_latitude,
                station_longitude,
            )["s12"]
            / 1000.0
        )
        if distance < min_distance:
            min_distance = distance
            nearest_station = station
    return nearest_station, min_distance


def calculate_cost_taxi(distance):
    if distance <= 1.8:
        return 11.0
    elif distance <= 10:
        return 11.0 + (distance - 1.8) * 3.5
    else:
        return 11.0 + (10 - 1.8) * 3.5 + (distance - 10) * 4.5


def calculate_cost(distance):
    if distance <= 4:
        return 2
    elif distance <= 9:
        return 3
    elif distance <= 14:
        return 4
    elif distance <= 21:
        return 5
    elif distance <= 28:
        return 6
    elif distance <= 37:
        return 7
    elif distance <= 48:
        return 8
    elif distance <= 61:
        return 9
    else:
        extra_distance = distance - 61
        extra_cost = (extra_distance + 14) // 15
        return 9 + extra_cost


class Transportation:
    def __init__(
        self, base_path: str = None, en_version=False, lang=None
    ):
        self.lang = normalize_lang(lang, en_version=en_version)
        if base_path is None:
            base_path = relative_database_path(self.lang, "transportation")
        self.city_list = CITY_SLUGS
        self.city_list_chinese = city_names(self.lang)

        curdir = os.path.dirname(os.path.realpath(__file__))
        SUBWAY_PATH = os.path.join(curdir, base_path, "subways.json")
        self.city_stations_dict = {}
        self.city_lines_dict = {}
        self.city_station_to_line = {}
        for city in self.city_list:
            stations_all, metro_lines, station_to_line = get_lines_and_stations(
                city, SUBWAY_PATH
            )
            self.city_stations_dict[city] = stations_all
            self.city_lines_dict[city] = metro_lines
            self.city_station_to_line[city] = station_to_line

        self.graphs = {}
        for city in self.city_list:
            self.graphs[city] = build_graph(self.city_lines_dict[city])

        self.poi_search = Poi(lang=self.lang)
        self._nearest_station_cache = {}

    def _find_nearest_station(self, city, location_name, location):
        cache_key = (city, location_name)
        if cache_key not in self._nearest_station_cache:
            self._nearest_station_cache[cache_key] = find_nearest_station(
                location,
                self.city_stations_dict[city],
            )
        return self._nearest_station_cache[cache_key]

    def goto(self, city, start, end, start_time, transport_type, verbose=False):
        if transport_type not in ["walk", "metro", "taxi"]:
            return "only support transport_type in ['walk','metro','taxi']"
        locationA = start
        locationB = end
        coordinate_A = self.poi_search.search(city, locationA)
        coordinate_B = self.poi_search.search(city, locationB)
        city_cn = city
        if city in self.city_list_chinese:
            city = self.city_list[self.city_list_chinese.index(city)]
        elif isinstance(city, str) and city.lower() in self.city_list:
            city = city.lower()
        locationA_name, locationB_name = locationA, locationB
        locationA, locationB = coordinate_A, coordinate_B
        transports = []
        if transport_type == "walk":
            distance = geodesic(locationA, locationB).kilometers
            walking_speed = 5.0
            time = distance / walking_speed
            cost = 0.0
            end_time = add_time(start_time, time)
            transport = {
                "start": locationA_name,
                "end": locationB_name,
                "mode": "walk",
                "start_time": start_time,
                "end_time": end_time,
                "cost": cost,
                "distance": distance,
            }
            transports.append(transport)
            if verbose:
                print(
                    "Walk Distance {:.3} kilometers, Time {:.3} hour, Cost {}¥".format(
                        distance, time, int(cost)
                    )
                )
            return transports

        elif transport_type == "taxi":
            distance = geodesic(locationA, locationB).kilometers
            taxi_speed = 40.0
            time = distance / taxi_speed
            cost = calculate_cost_taxi(distance)
            end_time = add_time(start_time, time)
            transport = {
                "start": locationA_name,
                "end": locationB_name,
                "mode": "taxi",
                "start_time": start_time,
                "end_time": end_time,
                "cost": round(cost, 2),
                "distance": round(distance, 2),
            }
            transports.append(transport)
            if verbose:
                print(
                    "Taxi Distance {:.3} kilometers, Time {:.2} hour, Cost {}¥".format(
                        distance, time, int(cost)
                    )
                )
            return transports

        elif transport_type == "metro":
            graph = self.graphs[city]
            stationA, distanceA = self._find_nearest_station(
                city,
                locationA_name,
                locationA,
            )
            stationB, distanceB = self._find_nearest_station(
                city,
                locationB_name,
                locationB,
            )
            if stationA == stationB:
                if verbose:
                    print("Too near. Walk.")
                return "No solution"
                return self.goto(
                    city_cn,
                    locationA_name,
                    locationB_name,
                    start_time,
                    transport_type="walk",
                    verbose=verbose,
                )
            shortest_path = find_shortest_path(
                graph, stationA["name"], stationB["name"]
            )
            if stationA and stationB:
                distance_between_stations = geodesic(
                    stationA["position"], stationB["position"]
                ).kilometers
                subway_speed = 30.0
                time_between_stations = distance_between_stations / subway_speed
                walking_speed = 5.0
                timeA = distanceA / walking_speed
                timeB = distanceB / walking_speed
                total_time = timeA + time_between_stations + timeB
                cost = calculate_cost(distance_between_stations)
                distance = distanceA + distance_between_stations + distanceB
                end_timeA = add_time(start_time, timeA)
                end_timeB = add_time(end_timeA, time_between_stations)
                end_time_final = add_time(end_timeB, timeB)
                end_time = end_time_final
                transports.append(
                    {
                        "start": locationA_name,
                        "end": stationA["name"] + self._metro_station_suffix(),
                        "mode": "walk",
                        "start_time": start_time,
                        "end_time": end_timeA,
                        "cost": 0,
                        "distance": round(distanceA, 2),
                    }
                )
                transports.append(
                    {
                        "start": stationA["name"] + self._metro_station_suffix(),
                        "end": stationB["name"] + self._metro_station_suffix(),
                        "mode": "metro",
                        "start_time": end_timeA,
                        "end_time": end_timeB,
                        "cost": cost,
                        "distance": round(distance_between_stations, 2),
                    }
                )
                transports.append(
                    {
                        "start": stationB["name"] + self._metro_station_suffix(),
                        "end": locationB_name,
                        "mode": "walk",
                        "start_time": end_timeB,
                        "end_time": end_time,
                        "cost": 0,
                        "distance": round(distanceB, 2),
                    }
                )
                if verbose:
                    print(
                        "Walk: From starting point to metro {}, Distance: {}.".format(
                            stationA["name"] + self._metro_station_suffix(), distanceA
                        )
                    )
                    print(
                        f"Subway: From {stationA['name'] + self._metro_station_suffix()} to {stationB['name'] + self._metro_station_suffix()}: {' -> '.join(shortest_path)}"
                    )
                    print("The cost of subway: {}¥".format(cost))
                    print(
                        "Walk: From metro {} to ending point,  Distance: {}.".format(
                            stationB["name"] + self._metro_station_suffix(), distanceB
                        )
                    )
                return transports
            else:
                raise NotImplementedError

    def _metro_station_suffix(self):
        return "-Metro Station" if self.lang == "en" else "-地铁站"
