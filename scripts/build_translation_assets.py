#!/usr/bin/env python3
import argparse
import ast
import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from ast import literal_eval
from pathlib import Path
import traceback

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PROJECT_ROOT.parent
CHINATRAVEL_ROOT = PROJECT_ROOT
ZH_DB = CHINATRAVEL_ROOT / "chinatravel" / "environment" / "database"
EN_DB = CHINATRAVEL_ROOT / "chinatravel" / "environment" / "database_en"

CITY_SLUGS = [
    "beijing",
    "shanghai",
    "nanjing",
    "suzhou",
    "hangzhou",
    "shenzhen",
    "chengdu",
    "wuhan",
    "guangzhou",
    "chongqing",
]

CITY_ZH = ["北京", "上海", "南京", "苏州", "杭州", "深圳", "成都", "武汉", "广州", "重庆"]
CITY_EN = [
    "Beijing",
    "Shanghai",
    "Nanjing",
    "Suzhou",
    "Hangzhou",
    "Shenzhen",
    "Chengdu",
    "Wuhan",
    "Guangzhou",
    "Chongqing",
]

CJK_RE = re.compile(r"[\u3400-\u9fff]")

CONCEPT_FIELD_ALIASES = {
    ("attraction", "type"): {
        "Art Museum": "Art museum",
        "Cultural Attractions": "Cultural Landscape",
        "Historical Site": "historical site",
        "Natural Scenery": "natural scenery",
        "Park": "park",
        "red tourism sites": "Red tourism sites",
        "university campus": "University campus",
    },
    ("restaurant", "cuisine"): {
        "Bread and Desserts": "Bakery and Desserts",
        "cafe": "coffee shop",
        "Fast food and simple meals": "Fast food and casual dining",
        "hot pot": "Hot pot",
    },
    ("accommodation", "featurehoteltype"): {
        "Air Purifier": "Air purifier",
        "Bed and Breakfast": "homestay",
        "Bed and breakfast": "homestay",
        "Designer Hotel": "Designer hotel",
        "Family Theme Room": "Family-themed room",
        "Family-themed Room": "Family-themed room",
        "Great View from the Window": "Great view from the window",
        "Scenic Window View": "Great view from the window",
        "Instagrammable swimming pool": "Instagrammable pool",
        "Chess and Card Room": "Mahjong and Card Game Room",
        "Mahjong and Card Room": "Mahjong and Card Game Room",
        "Serviced Apartment": "Hotel Apartment",
        "small but beautiful": "small and beautiful",
        "SPA": "Spa",
        "Stunning night views": "Stunning Night Views",
        "Swimming pool": "Swimming Pool",
        "viral swimming pool": "Instagrammable pool",
    },
}

CONCEPT_LITERAL_ALIASES = {}
for field_aliases in CONCEPT_FIELD_ALIASES.values():
    CONCEPT_LITERAL_ALIASES.update(field_aliases)

QUERY_CONCEPT_REPLACEMENTS = [
    (re.compile(r"\bSwimming pool\b"), "Swimming Pool"),
    (re.compile(r"\bswimming pool\b"), "Swimming Pool"),
    (re.compile(r"\bFamily-themed Room\b"), "Family-themed room"),
    (re.compile(r"\bcafes\b"), "coffee shops"),
    (re.compile(r"\bcafe\b"), "coffee shop"),
    (re.compile(r"\buniversity campuses\b"), "University campus"),
    (re.compile(r"\buniversity campus\b"), "University campus"),
    (re.compile(r"\bCultural Landscapes\b"), "Cultural Landscape"),
    (re.compile(r"\bcultural landscapes\b"), "Cultural Landscape"),
    (re.compile(r"\bred tourism sites\b"), "Red tourism sites"),
    (re.compile(r"\bhot pot\b"), "Hot pot"),
    (re.compile(r"\bFast food and simple meals\b"), "Fast food and casual dining"),
    (re.compile(r"\bBread and Desserts\b"), "Bakery and Desserts"),
]


def read_csv_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def write_record_folder(path, records):
    path.mkdir(parents=True, exist_ok=True)
    for uid, data in records.items():
        write_json(path / "{}.json".format(uid), data)


def display_path(path):
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def has_cjk(value):
    return isinstance(value, str) and CJK_RE.search(value) is not None


def normalize_concept_field(category, field, value):
    if not isinstance(value, str):
        return value
    value = value.strip()
    return CONCEPT_FIELD_ALIASES.get((category, field), {}).get(value, value)


def normalize_dsl_concept_literals(code):
    if not isinstance(code, str):
        return code
    normalized = code
    for alias, canonical in CONCEPT_LITERAL_ALIASES.items():
        for quote in ("'", '"'):
            normalized = normalized.replace(
                "{}{}{}".format(quote, alias, quote),
                "{}{}{}".format(quote, canonical, quote),
            )
    return normalized


def normalize_query_concept_terms(text):
    if not isinstance(text, str):
        return text
    normalized = text
    for pattern, replacement in QUERY_CONCEPT_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


class TranslationDictionary:
    def __init__(self):
        self.term_map = {}
        self.sources = {}
        self.conflicts = []

    def add(self, zh, en, category, source):
        if not zh or not en or zh == en or not has_cjk(zh):
            return
        zh = str(zh).strip()
        en = str(en).strip()
        if not zh or not en or zh == en:
            return
        old = self.term_map.get(zh)
        if old is not None and old != en:
            self.conflicts.append(
                {"zh": zh, "existing_en": old, "new_en": en, "category": category, "source": source}
            )
            return
        self.term_map[zh] = en
        self.sources.setdefault(zh, []).append({"en": en, "category": category, "source": source})

    def as_json(self):
        return {
            "term_map": dict(sorted(self.term_map.items(), key=lambda item: item[0])),
            "sources": self.sources,
        }


def add_csv_pairs(dictionary, category, zh_path, en_path, key_fields):
    zh_rows = read_csv_rows(zh_path)
    en_rows = read_csv_rows(en_path)
    en_by_id = {row.get("id"): row for row in en_rows if row.get("id") is not None}
    for idx, zh_row in enumerate(zh_rows):
        en_row = en_by_id.get(zh_row.get("id"))
        if en_row is None and idx < len(en_rows):
            en_row = en_rows[idx]
        if en_row is None:
            continue
        for field in key_fields:
            en_value = normalize_concept_field(category, field, en_row.get(field))
            dictionary.add(
                zh_row.get(field),
                en_value,
                category,
                "{}:{}:{}".format(zh_path.relative_to(PROJECT_ROOT), zh_row.get("id"), field),
            )


def add_ordered_json_name_pairs(dictionary, category, zh_path, en_path):
    zh_items = read_json(zh_path)
    en_items = read_json(en_path)
    for idx, (zh_item, en_item) in enumerate(zip(zh_items, en_items)):
        dictionary.add(
            zh_item.get("name"),
            en_item.get("name"),
            category,
            "{}:{}".format(zh_path.relative_to(PROJECT_ROOT), idx),
        )


def add_transport_pairs(dictionary):
    zh_airplanes = [json.loads(line) for line in (ZH_DB / "intercity_transport" / "airplane.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    en_airplanes = [json.loads(line) for line in (EN_DB / "intercity_transport" / "airplane.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    en_by_id = {row["FlightID"]: row for row in en_airplanes}
    for row in zh_airplanes:
        en_row = en_by_id.get(row["FlightID"])
        if not en_row:
            continue
        for field in ["From", "To"]:
            dictionary.add(row.get(field), en_row.get(field), "airplane", "airplane.jsonl:{}".format(row["FlightID"]))

    for train_path in sorted((ZH_DB / "intercity_transport" / "train").glob("*.json")):
        en_path = EN_DB / "intercity_transport" / "train" / train_path.name
        if not en_path.exists():
            continue
        zh_rows = read_json(train_path)
        en_rows = read_json(en_path)
        en_by_id = {row.get("TrainID"): row for row in en_rows}
        for idx, zh_row in enumerate(zh_rows):
            en_row = en_by_id.get(zh_row.get("TrainID"))
            if en_row is None and idx < len(en_rows):
                en_row = en_rows[idx]
            if en_row is None:
                continue
            for field in ["TrainType", "From", "To"]:
                dictionary.add(
                    zh_row.get(field),
                    en_row.get(field),
                    "train",
                    "{}:{}:{}".format(train_path.relative_to(PROJECT_ROOT), zh_row.get("TrainID"), field),
                )


def add_subway_pairs(dictionary):
    zh = read_json(ZH_DB / "transportation" / "subways.json")
    en = read_json(EN_DB / "transportation" / "subways.json")
    for city in CITY_SLUGS:
        for line_idx, zh_line in enumerate(zh.get(city, [])):
            if line_idx >= len(en.get(city, [])):
                continue
            en_line = en[city][line_idx]
            dictionary.add(zh_line.get("name"), en_line.get("name"), "subway_line", "subways.json:{}:line{}".format(city, line_idx))
            for station_idx, zh_station in enumerate(zh_line.get("stations", [])):
                if station_idx >= len(en_line.get("stations", [])):
                    continue
                en_station = en_line["stations"][station_idx]
                dictionary.add(
                    zh_station.get("name"),
                    en_station.get("name"),
                    "subway_station",
                    "subways.json:{}:line{}:station{}".format(city, line_idx, station_idx),
                )
                dictionary.add(
                    "{}-地铁站".format(zh_station.get("name")),
                    "{}-Metro Station".format(en_station.get("name")),
                    "subway_station_suffix",
                    "subways.json:{}:line{}:station{}".format(city, line_idx, station_idx),
                )


def build_dictionary():
    dictionary = TranslationDictionary()
    for zh, en in zip(CITY_ZH, CITY_EN):
        dictionary.add(zh, en, "city", "city_list")

    for city in CITY_SLUGS:
        add_csv_pairs(
            dictionary,
            "attraction",
            ZH_DB / "attractions" / city / "attractions.csv",
            EN_DB / "attractions" / city / "attractions.csv",
            ["name", "type"],
        )
        add_csv_pairs(
            dictionary,
            "restaurant",
            ZH_DB / "restaurants" / city / "restaurants_{}.csv".format(city),
            EN_DB / "restaurants" / city / "restaurants_{}.csv".format(city),
            ["name", "cuisine"],
        )
        add_csv_pairs(
            dictionary,
            "accommodation",
            ZH_DB / "accommodations" / city / "accommodations.csv",
            EN_DB / "accommodations" / city / "accommodations.csv",
            ["name", "hotelname_en", "featurehoteltype"],
        )
        add_ordered_json_name_pairs(
            dictionary,
            "poi",
            ZH_DB / "poi" / city / "poi.json",
            EN_DB / "poi" / city / "poi.json",
        )

    add_transport_pairs(dictionary)
    add_subway_pairs(dictionary)
    return dictionary


def extract_string_literals(code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
    return values


def translate_dsl_code(code, term_map):
    translated = code
    matched = []
    for zh in sorted(term_map, key=len, reverse=True):
        if zh in translated:
            translated = translated.replace(zh, term_map[zh])
            matched.append(zh)
    translated = normalize_dsl_concept_literals(translated)
    unresolved = sorted({value for value in extract_string_literals(translated) if has_cjk(value)})
    return translated, matched, unresolved


def replace_terms(text, term_map):
    if not isinstance(text, str):
        return text
    translated = text
    for zh in sorted(term_map, key=len, reverse=True):
        if zh in translated:
            translated = translated.replace(zh, term_map[zh])
    return translated


def local_records(input_data_dir):
    root = Path(input_data_dir)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    records = []
    for path in sorted(root.rglob("*.json")):
        if "{}en{}".format(os.sep, os.sep) in str(path):
            continue
        try:
            data = read_json(path)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("uid"):
            records.append((path, data))
    return records


def hf_records(splits, config_name):
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "datasets is required for --source hf. Install project requirements or use --source local."
        ) from exc

    records = []
    for split in splits:
        dataset = load_dataset("LAMDA-NeSy/ChinaTravel", name=config_name, split=split)
        for row in dataset.to_list():
            data = dict(row)
            if isinstance(data.get("hard_logic_py"), str):
                try:
                    data["hard_logic_py"] = literal_eval(data["hard_logic_py"])
                except (ValueError, SyntaxError):
                    pass
            records.append((Path("huggingface") / config_name / split / "{}.json".format(data.get("uid", "")), data))
    return records


def translate_query_deepseek(uid, text, api_key, model, term_map, retries=3):
    if not text:
        raise ValueError("text is empty")
    canonicalized_text = replace_terms(text, term_map)
    prompt = (
        "Translate Chinese travel-planning benchmark queries into natural English.\n"
        "Preserve existing English city names, POI names, numbers, budgets, constraints, and intent.\n"
        "If the query already contains English terms inserted from the dictionary, keep their exact wording and capitalization.\n"
        "Return only the translated query.\n\n"
        "Query:\n{}\n\nTranslation:".format(canonicalized_text)
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 512,
        "thinking": {"type": "enabled"},
    }
    body = json.dumps(payload).encode("utf-8")
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                "https://api.deepseek.com/chat/completions",
                data=body,
                headers={
                    "Authorization": "Bearer {}".format(api_key),
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
                res = data["choices"][0]["message"]["content"].strip()
                if not res:
                    raise ValueError("DeepSeek returned an empty translation")
                return normalize_query_concept_terms(res)
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            KeyError,
            IndexError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            last_error = exc
            traceback.print_exc()
            if attempt == retries - 1:
                raise RuntimeError("DeepSeek translation failed for {}: {}".format(uid, exc)) from exc
            time.sleep(2 ** attempt)
    raise RuntimeError("DeepSeek translation failed for {}: {}".format(uid, last_error)) from last_error


def translate_queries(records, args, term_map):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if args.no_api or not api_key:
        return {}, [
            {
                "uid": data.get("uid"),
                "reason": "DEEPSEEK_API_KEY not set" if not api_key else "API disabled",
            }
            for _, data in records
            if data.get("nature_language")
        ]

    translations = {}
    failures = []
    executor = ThreadPoolExecutor(max_workers=args.workers)
    try:
        futures = {
            executor.submit(
                translate_query_deepseek,
                data["uid"],
                data.get("nature_language", ""),
                api_key,
                args.model,
                term_map,
            ): data
            for _, data in records
            if data.get("nature_language")
        }
        completed = as_completed(futures)
        if tqdm is not None:
            completed = tqdm(completed, total=len(futures), desc="Translating queries")
        for future in completed:
            data = futures[future]
            uid = data["uid"]
            try:
                translated = future.result()
                if not translated or not translated.strip():
                    raise RuntimeError("empty translation")
                translations[uid] = translated
            except Exception as exc:
                failures.append({"uid": uid, "reason": str(exc)})
    except KeyboardInterrupt:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=False)
    return translations, failures


def load_existing_query_translations(output_dir):
    path = output_dir / "translated_nature_language.json"
    if not path.exists():
        return {}, []
    data = read_json(path)
    translations = {}
    empty_uids = []
    for uid, value in data.items():
        if isinstance(value, str) and value.strip():
            translations[uid] = normalize_query_concept_terms(value)
        else:
            empty_uids.append(uid)
    return translations, empty_uids


def build_translated_records(records, term_map, query_translations):
    translated_records = {}
    unresolved = []
    untranslated_query_uids = []
    for path, data in records:
        uid = data["uid"]
        out = dict(data)
        for key, value in list(out.items()):
            if key in {"nature_language", "hard_logic_py"}:
                continue
            if isinstance(value, str):
                out[key] = replace_terms(value, term_map)
            elif isinstance(value, list):
                out[key] = [replace_terms(item, term_map) if isinstance(item, str) else item for item in value]
        translated_query = query_translations.get(uid)
        if isinstance(translated_query, str) and translated_query.strip():
            out["nature_language"] = normalize_query_concept_terms(translated_query)
        elif data.get("nature_language"):
            untranslated_query_uids.append(uid)
        hard_logic_py = data.get("hard_logic_py", [])
        if isinstance(hard_logic_py, str):
            hard_logic_py = [hard_logic_py]
        translated_logic = []
        for idx, code in enumerate(hard_logic_py):
            translated_code, matched, missing = translate_dsl_code(str(code), term_map)
            translated_logic.append(translated_code)
            if missing:
                unresolved.append(
                    {
                        "uid": uid,
                        "path": display_path(path),
                        "hard_logic_py_index": idx,
                        "unresolved_literals": missing,
                        "original": code,
                        "translated": translated_code,
                    }
                )
        if translated_logic:
            out["hard_logic_py"] = translated_logic
        translated_records[uid] = out
    return translated_records, unresolved, untranslated_query_uids


def main():
    parser = argparse.ArgumentParser(description="Build Chinese-to-English DSL translation assets.")
    parser.add_argument("--source", choices=["local", "hf"], default="local", help="Source for Chinese query JSON records.")
    parser.add_argument("--input-data-dir", default="TPC_IJCAI_2026_phase1", help="Chinese query JSON root.")
    parser.add_argument("--hf-splits", default="easy,medium,human,preference_base50", help="Comma-separated HF splits when --source hf.")
    parser.add_argument("--hf-config", default="default", help="HF dataset config when --source hf.")
    parser.add_argument("--output-dir", default="translation_artifacts_phase1", help="Output artifact directory.")
    parser.add_argument("--workers", type=int, default=32, help="Concurrent DeepSeek query translations.")
    parser.add_argument("--model", default="deepseek-v4-flash", help="DeepSeek model name.")
    parser.add_argument("--no-api", action="store_true", help="Skip query translation API calls.")
    parser.add_argument(
        "--no-reuse-existing-translations",
        action="store_true",
        help="Ignore existing non-empty translated_nature_language.json entries.",
    )
    args = parser.parse_args()

    output_dir = PROJECT_ROOT / args.output_dir
    dictionary = build_dictionary()
    write_json(output_dir / "dsl_translation_dictionary.json", dictionary.as_json())
    write_json(output_dir / "dictionary_conflicts.json", dictionary.conflicts)

    if args.source == "hf":
        records = hf_records([split.strip() for split in args.hf_splits.split(",") if split.strip()], args.hf_config)
    else:
        records = local_records(args.input_data_dir)
    existing_translations = {}
    empty_existing_uids = []
    if not args.no_reuse_existing_translations:
        existing_translations, empty_existing_uids = load_existing_query_translations(output_dir)
    pending_records = [
        (path, data)
        for path, data in records
        if data.get("nature_language") and data.get("uid") not in existing_translations
    ]
    new_query_translations, query_failures = translate_queries(pending_records, args, dictionary.term_map)
    query_translations = dict(existing_translations)
    query_translations.update(new_query_translations)
    translated_records, unresolved, untranslated_query_uids = build_translated_records(records, dictionary.term_map, query_translations)
    final_data_ready = len(untranslated_query_uids) == 0

    write_json(output_dir / "translated_queries.json", translated_records)
    if final_data_ready:
        write_record_folder(output_dir / "translated_data", translated_records)
        translated_data_dir = output_dir / "translated_data"
    else:
        write_record_folder(output_dir / "translated_data_partial", translated_records)
        translated_data_dir = output_dir / "translated_data_partial"
    write_json(output_dir / "translated_nature_language.json", query_translations)
    write_json(output_dir / "query_translation_failures.json", query_failures)
    write_json(output_dir / "untranslated_query_uids.json", untranslated_query_uids)
    write_json(output_dir / "unresolved_hard_logic_literals.json", unresolved)
    write_json(
        output_dir / "summary.json",
        {
            "dictionary_terms": len(dictionary.term_map),
            "dictionary_conflicts": len(dictionary.conflicts),
            "source_records": len(records),
            "final_data_ready": final_data_ready,
            "translated_data_dir": display_path(translated_data_dir),
            "reused_existing_translations": len(existing_translations),
            "empty_existing_translations": len(empty_existing_uids),
            "newly_translated_queries": len(new_query_translations),
            "translated_queries": len(query_translations),
            "query_translation_failures": len(query_failures),
            "untranslated_queries": len(untranslated_query_uids),
            "unresolved_hard_logic_entries": len(unresolved),
        },
    )

    print("Wrote translation assets to {}".format(display_path(output_dir)))
    print("Dictionary terms: {}".format(len(dictionary.term_map)))
    print("Source records: {}".format(len(records)))
    print("Reused existing translations: {}".format(len(existing_translations)))
    print("Empty existing translations: {}".format(len(empty_existing_uids)))
    print("Newly translated queries: {}".format(len(new_query_translations)))
    print("Translated queries: {}".format(len(query_translations)))
    print("Untranslated queries: {}".format(len(untranslated_query_uids)))
    print("Data folder: {}".format(display_path(translated_data_dir)))
    print("Unresolved hard_logic_py entries: {}".format(len(unresolved)))


if __name__ == "__main__":
    main()
