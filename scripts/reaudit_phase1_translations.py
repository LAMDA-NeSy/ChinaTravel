#!/usr/bin/env python3
"""Conservatively re-audit Phase 1 LLM-invalid translations with thinking."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from audit_phase1_translations import (
    PROJECT_ROOT,
    load_audit_config,
    merged_audit_api_config,
    read_json,
)
from openai_compatible_api import (
    build_api_headers,
    build_chat_completion_payload,
    resolve_chat_completions_url,
)

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


VERDICTS = {
    "translation_error",
    "acceptable",
    "data_conflict",
    "source_ambiguous",
    "needs_review",
}
ACTIONS = {
    "keep_original",
    "use_repaired",
    "rewrite",
    "fix_dictionary_or_oracle",
    "manual_review",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "translation_api_config.json",
    )
    parser.add_argument(
        "--no-reuse",
        action="store_true",
        help="Ignore cached thinking re-audit results.",
    )
    return parser.parse_args()


def resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def public_result(result: dict | None) -> dict | None:
    if result is None:
        return None
    return {
        key: value
        for key, value in result.items()
        if key not in {"raw_content", "input_fingerprint"}
    }


def api_fingerprint(api_config: dict) -> dict:
    return {
        "provider": api_config.get("provider", "openai_compatible"),
        "endpoint": resolve_chat_completions_url(api_config),
        "model": api_config.get("model"),
        "temperature": api_config.get("temperature"),
        "max_tokens": api_config.get("max_tokens"),
        "max_tokens_field": api_config.get("max_tokens_field", "max_tokens"),
        "extra_body": api_config.get("extra_body", {}),
    }


def input_fingerprint(
    *,
    stage: str,
    prompt_version: int,
    api_config: dict,
    payload: dict,
) -> str:
    data = {
        "stage": stage,
        "prompt_version": prompt_version,
        "api": api_fingerprint(api_config),
        "payload": payload,
    }
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def extract_json_object(content: str) -> dict:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(
            r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE
        )
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("response does not contain a JSON object")
    data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("response JSON is not an object")
    return data


def normalize_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return [str(item) for item in value]


def normalize_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def parse_blind_result(content: str) -> dict:
    data = extract_json_object(content)
    verdict = str(data.get("verdict", "")).strip().casefold()
    if verdict not in VERDICTS:
        raise ValueError(f"invalid blind-review verdict: {verdict!r}")
    return {
        "verdict": verdict,
        "issue_codes": normalize_string_list(
            data.get("issue_codes", []), "issue_codes"
        ),
        "material_differences": normalize_string_list(
            data.get("material_differences", []),
            "material_differences",
        ),
        "explanation": str(data.get("explanation", "")).strip(),
        "confidence": normalize_confidence(data.get("confidence")),
    }


def parse_adjudication_result(content: str) -> dict:
    data = extract_json_object(content)
    verdict = str(data.get("verdict", "")).strip().casefold()
    if verdict not in VERDICTS:
        raise ValueError(f"invalid adjudication verdict: {verdict!r}")
    action = str(data.get("recommended_action", "")).strip().casefold()
    if action not in ACTIONS:
        raise ValueError(f"invalid recommended_action: {action!r}")
    change_necessary = data.get("change_necessary")
    if not isinstance(change_necessary, bool):
        raise ValueError("change_necessary must be a boolean")
    return {
        "verdict": verdict,
        "recommended_action": action,
        "change_necessary": change_necessary,
        "recommended_translation": str(
            data.get("recommended_translation", "")
        ).strip(),
        "issue_codes": normalize_string_list(
            data.get("issue_codes", []), "issue_codes"
        ),
        "material_differences": normalize_string_list(
            data.get("material_differences", []),
            "material_differences",
        ),
        "explanation": str(data.get("explanation", "")).strip(),
        "confidence": normalize_confidence(data.get("confidence")),
    }


def request_review(
    prompt: str,
    *,
    api_key: str | None,
    api_config: dict,
    parser,
) -> dict:
    payload = build_chat_completion_payload(
        api_config,
        model=api_config["model"],
        messages=[{"role": "user", "content": prompt}],
        default_temperature=0.0,
    )
    request_body = json.dumps(payload).encode("utf-8")
    endpoint_url = resolve_chat_completions_url(api_config)
    headers = build_api_headers(api_config, api_key)
    retries = int(api_config.get("retries", 3))
    timeout = float(api_config.get("timeout_seconds", 120))
    accepted_finish_reasons = set(
        api_config.get("accepted_finish_reasons", ["stop"])
    )
    last_error = None
    for retry in range(retries):
        try:
            request = urllib.request.Request(
                endpoint_url,
                data=request_body,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            choice = response_data["choices"][0]
            finish_reason = choice.get("finish_reason")
            if finish_reason not in accepted_finish_reasons:
                raise ValueError(
                    f"unaccepted finish_reason={finish_reason!r}"
                )
            content = choice["message"]["content"]
            parsed = parser(content)
            parsed.update(
                {
                    "finish_reason": finish_reason,
                    "model": response_data.get(
                        "model", api_config["model"]
                    ),
                    "usage": response_data.get("usage", {}),
                    "raw_content": content,
                }
            )
            return parsed
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            last_error = exc
            if retry + 1 < retries:
                time.sleep(2**retry)
    raise RuntimeError(
        f"thinking re-audit failed after {retries} retries: {last_error}"
    )


def blind_payload(item: dict) -> dict:
    source = item["source"]
    translated = item["translated"]
    return {
        "uid": item["uid"],
        "metadata": {
            "start_city_zh": source.get("start_city"),
            "start_city_en": translated.get("start_city"),
            "target_city_zh": source.get("target_city"),
            "target_city_en": translated.get("target_city"),
            "days": source.get("days"),
            "people_number": source.get("people_number"),
        },
        "chinese_query": source.get("nature_language", ""),
        "original_english_query": translated.get("nature_language", ""),
        "chinese_oracle_dsl": source.get("hard_logic_py", []),
        "english_oracle_dsl": translated.get("hard_logic_py", []),
    }


def blind_prompt(payload: dict, prompt_version: int) -> str:
    return (
        "You are the first independent reviewer in a conservative bilingual "
        "translation audit for ChinaTravel Phase 1. Think carefully before "
        "answering, but return only the requested JSON object.\n\n"
        "Review the ORIGINAL English query from scratch. Do not assume it is "
        "wrong merely because it was selected for review. A material translation "
        "error means an explicit fact, entity, number, negation, AND/OR relation, "
        "or constraint was omitted, added, or changed. Harmless paraphrases and "
        "ordinary English scope such as 'avoid A or B' are acceptable.\n\n"
        "Use the English Oracle DSL to understand canonical entity names and "
        "logical semantics. Canonical database names do not need to be literal "
        "word-for-word translations. If the Chinese query conflicts with the "
        "English Oracle DSL or canonical name mapping, return data_conflict, not "
        "translation_error. If the Chinese source template itself is malformed or "
        "cannot support a confident judgment, return source_ambiguous. Use "
        "needs_review for any other unresolved case.\n\n"
        "Return exactly one JSON object:\n"
        '{"verdict":"translation_error|acceptable|data_conflict|'
        'source_ambiguous|needs_review","issue_codes":["..."],'
        '"material_differences":["..."],"explanation":"...",'
        '"confidence":0.0}\n\n'
        f"Prompt version: {prompt_version}\n"
        "Review input:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def compact_repair_result(repair: dict | None) -> dict | None:
    if repair is None:
        return None
    return {
        "status": repair.get("status"),
        "original_translation": repair.get("original_translation"),
        "repaired_translation": repair.get("repaired_translation"),
        "attempts": [
            {
                "attempt": attempt.get("attempt"),
                "candidate_translation": attempt.get(
                    "candidate_translation"
                ),
                "accepted": attempt.get("accepted"),
                "error": attempt.get("error"),
                "validation": attempt.get("validation"),
            }
            for attempt in repair.get("attempts", [])
        ],
    }


def adjudication_payload(item: dict, blind_result: dict) -> dict:
    payload = blind_payload(item)
    payload.update(
        {
            "initial_non_thinking_audit": public_result(
                item["initial_audit"]
            ),
            "independent_thinking_review": public_result(blind_result),
            "repair_evidence": compact_repair_result(item.get("repair")),
        }
    )
    return payload


def adjudication_prompt(payload: dict, prompt_version: int) -> str:
    return (
        "You are the final conservative adjudicator for a bilingual benchmark "
        "translation audit. Think carefully before answering, but return only the "
        "requested JSON object.\n\n"
        "The goal is to modify as little released data as possible. Start from "
        "the presumption that the ORIGINAL English query should be kept. Recommend "
        "a change only when the original has a clear material omission or semantic "
        "change, not for style, awkward wording, literal-vs-canonical entity names, "
        "or a debatable interpretation. Treat a Chinese/Oracle/canonical-name "
        "mismatch as data_conflict. Treat a malformed source template as "
        "source_ambiguous. Resolve disagreements between the prior audits using "
        "the actual Chinese query and Oracle DSL evidence.\n\n"
        "recommended_action must be one of:\n"
        "- keep_original: the original is materially acceptable.\n"
        "- use_repaired: an accepted repaired translation is clearly necessary "
        "and correct.\n"
        "- rewrite: a change is clearly necessary but no accepted repair is safe.\n"
        "- fix_dictionary_or_oracle: source and canonical/Oracle data conflict.\n"
        "- manual_review: ambiguity remains.\n\n"
        "Set change_necessary=true only for a clear translation_error. When the "
        "action is use_repaired or rewrite, provide the exact proposed English in "
        "recommended_translation. Otherwise use an empty string.\n\n"
        "Return exactly one JSON object:\n"
        '{"verdict":"translation_error|acceptable|data_conflict|'
        'source_ambiguous|needs_review","recommended_action":'
        '"keep_original|use_repaired|rewrite|fix_dictionary_or_oracle|'
        'manual_review","change_necessary":false,'
        '"recommended_translation":"","issue_codes":["..."],'
        '"material_differences":["..."],"explanation":"...",'
        '"confidence":0.0}\n\n'
        f"Prompt version: {prompt_version}\n"
        "Adjudication input:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def load_cached_result(
    path: Path, fingerprint: str, *, adjudication: bool
) -> dict | None:
    if not path.is_file():
        return None
    try:
        result = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if result.get("input_fingerprint") != fingerprint:
        return None
    if result.get("audit_error"):
        return None
    if result.get("verdict") not in VERDICTS:
        return None
    if adjudication and result.get("recommended_action") not in ACTIONS:
        return None
    return result


def run_stage(
    items: list[dict],
    *,
    stage: str,
    prompt_version: int,
    output_dir: Path,
    api_key: str | None,
    api_config: dict,
    reuse: bool,
    payload_builder,
    prompt_builder,
    parser,
    adjudication: bool,
) -> tuple[dict[str, dict], dict]:
    cache_dir = output_dir / f"{stage}_results"
    cache_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    pending = []
    cached_count = 0
    for item in items:
        payload = payload_builder(item)
        fingerprint = input_fingerprint(
            stage=stage,
            prompt_version=prompt_version,
            api_config=api_config,
            payload=payload,
        )
        cache_path = cache_dir / f"{item['uid']}.json"
        cached = (
            load_cached_result(
                cache_path,
                fingerprint,
                adjudication=adjudication,
            )
            if reuse
            else None
        )
        if cached is not None:
            results[item["uid"]] = cached
            cached_count += 1
        else:
            prompt = prompt_builder(payload, prompt_version)
            pending.append((item, prompt, fingerprint, cache_path))

    failures = []
    if pending and api_config.get("api_key_required", True) and not api_key:
        api_key_name = str(
            api_config.get("api_key_env", "OPENAI_API_KEY")
        )
        raise RuntimeError(
            f"{api_key_name} is not set; {len(pending)} {stage} reviews "
            "are pending"
        )
    workers = int(api_config.get("workers", 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                request_review,
                prompt,
                api_key=api_key,
                api_config=api_config,
                parser=parser,
            ): (item, fingerprint, cache_path)
            for item, prompt, fingerprint, cache_path in pending
        }
        completed = as_completed(futures)
        if tqdm is not None and futures:
            completed = tqdm(
                completed,
                total=len(futures),
                desc=f"Thinking re-audit: {stage}",
            )
        for future in completed:
            item, fingerprint, cache_path = futures[future]
            uid = item["uid"]
            try:
                result = future.result()
                result.update(
                    {
                        "uid": uid,
                        "index_1based": item["index_1based"],
                        "input_fingerprint": fingerprint,
                        "prompt_version": prompt_version,
                        "audited_at_utc": datetime.now(
                            timezone.utc
                        ).isoformat(),
                    }
                )
                write_json(cache_path, result)
            except Exception as exc:
                result = {
                    "uid": uid,
                    "index_1based": item["index_1based"],
                    "verdict": "needs_review",
                    "recommended_action": (
                        "manual_review" if adjudication else None
                    ),
                    "change_necessary": False if adjudication else None,
                    "recommended_translation": "" if adjudication else None,
                    "issue_codes": ["reaudit_request_error"],
                    "material_differences": [],
                    "explanation": str(exc),
                    "confidence": 0.0,
                    "audit_error": True,
                }
                failures.append(uid)
            results[uid] = result

    counts = Counter(result["verdict"] for result in results.values())
    stats = {
        "stage": stage,
        "requested": len(items),
        "cached": cached_count,
        "new": len(pending) - len(failures),
        "failures": len(failures),
        "failure_uids": failures,
        "verdict_counts": dict(sorted(counts.items())),
        "workers": workers,
        "cache_dir": str(cache_dir),
    }
    return results, stats


def proposed_translation(item: dict, adjudication: dict) -> str:
    action = adjudication.get("recommended_action")
    if action == "use_repaired":
        repair = item.get("repair") or {}
        return str(
            repair.get("repaired_translation")
            or adjudication.get("recommended_translation")
            or ""
        ).strip()
    if action == "rewrite":
        return str(adjudication.get("recommended_translation") or "").strip()
    return ""


def conservative_decision(
    item: dict,
    blind: dict,
    adjudication: dict,
    threshold: float,
) -> dict:
    original = str(item["translated"].get("nature_language", "")).strip()
    proposed = proposed_translation(item, adjudication)
    high_confidence_agreement = (
        blind.get("verdict") == "translation_error"
        and blind.get("confidence", 0.0) >= threshold
        and adjudication.get("verdict") == "translation_error"
        and adjudication.get("confidence", 0.0) >= threshold
        and adjudication.get("change_necessary") is True
        and adjudication.get("recommended_action")
        in {"use_repaired", "rewrite"}
        and bool(proposed)
        and proposed != original
    )
    verdicts = {blind.get("verdict"), adjudication.get("verdict")}
    if high_confidence_agreement:
        outcome = "change_recommended"
    elif "data_conflict" in verdicts:
        outcome = "data_conflict"
    elif "source_ambiguous" in verdicts:
        outcome = "source_ambiguous"
    elif adjudication.get("verdict") == "acceptable":
        outcome = "keep_original"
    else:
        outcome = "manual_review"
    return {
        "outcome": outcome,
        "change_recommended": high_confidence_agreement,
        "confidence_threshold": threshold,
        "proposed_translation": proposed if high_confidence_agreement else "",
        "reason": (
            "The blind review and final adjudication both support a material "
            "translation error above the configured confidence threshold."
            if high_confidence_agreement
            else "The conservative change threshold was not met."
        ),
    }


def markdown_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def write_outputs(
    output_dir: Path,
    report: dict,
) -> None:
    write_json(output_dir / "phase1_thinking_reaudit.json", report)
    records = report["records"]
    csv_fields = [
        "index_1based",
        "uid",
        "repair_status",
        "blind_verdict",
        "blind_confidence",
        "adjudication_verdict",
        "adjudication_confidence",
        "recommended_action",
        "outcome",
        "change_recommended",
        "original_english_query",
        "proposed_translation",
        "adjudication_explanation",
    ]
    with (output_dir / "phase1_thinking_reaudit.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=csv_fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "index_1based": record["index_1based"],
                    "uid": record["uid"],
                    "repair_status": record["repair_status"],
                    "blind_verdict": record["blind_review"]["verdict"],
                    "blind_confidence": record["blind_review"]["confidence"],
                    "adjudication_verdict": record["adjudication"]["verdict"],
                    "adjudication_confidence": record["adjudication"][
                        "confidence"
                    ],
                    "recommended_action": record["adjudication"].get(
                        "recommended_action"
                    ),
                    "outcome": record["decision"]["outcome"],
                    "change_recommended": record["decision"][
                        "change_recommended"
                    ],
                    "original_english_query": record[
                        "original_english_query"
                    ],
                    "proposed_translation": record["decision"][
                        "proposed_translation"
                    ],
                    "adjudication_explanation": record["adjudication"].get(
                        "explanation", ""
                    ),
                }
            )

    summary = report["summary"]
    lines = [
        "# Phase 1 Thinking Re-audit",
        "",
        f"- Selected initial-invalid records: {summary['selected']}",
        f"- Conservative changes recommended: {summary['change_recommended']}",
        f"- Keep original: {summary['keep_original']}",
        f"- Data conflicts: {summary['data_conflict']}",
        f"- Source ambiguities: {summary['source_ambiguous']}",
        f"- Manual review: {summary['manual_review']}",
        "- No data files were modified.",
        "",
        "| Index | UID | Blind review | Adjudication | Action | Outcome |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        blind = record["blind_review"]
        adjudication = record["adjudication"]
        lines.append(
            f"| {record['index_1based']} | `{record['uid']}` | "
            f"{markdown_cell(blind['verdict'])} ({blind['confidence']:.2f}) | "
            f"{markdown_cell(adjudication['verdict'])} "
            f"({adjudication['confidence']:.2f}) | "
            f"{markdown_cell(adjudication.get('recommended_action'))} | "
            f"{markdown_cell(record['decision']['outcome'])} |"
        )
    lines.append("")
    (output_dir / "phase1_thinking_reaudit.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    files = {
        "minimal_change_recommended_uids.txt": [
            record["uid"]
            for record in records
            if record["decision"]["outcome"] == "change_recommended"
        ],
        "keep_original_uids.txt": [
            record["uid"]
            for record in records
            if record["decision"]["outcome"] == "keep_original"
        ],
        "manual_review_uids.txt": [
            record["uid"]
            for record in records
            if record["decision"]["outcome"]
            in {"manual_review", "data_conflict", "source_ambiguous"}
        ],
    }
    for filename, uids in files.items():
        (output_dir / filename).write_text(
            "\n".join(uids) + ("\n" if uids else ""),
            encoding="utf-8",
        )


def main() -> int:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    config = load_audit_config(config_path)
    reaudit = config["audit"].get("reaudit")
    if not isinstance(reaudit, dict) or not reaudit.get("enabled", False):
        raise ValueError("audit.reaudit must be enabled in the configuration")
    if reaudit.get("auto_apply", False):
        raise ValueError("thinking re-audit never supports auto_apply=true")
    threshold = float(reaudit.get("confidence_threshold", 0.9))
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("audit.reaudit.confidence_threshold must be 0..1")

    api_config = merged_audit_api_config(config)
    reaudit_api = reaudit.get("api", {})
    if not isinstance(reaudit_api, dict):
        raise ValueError("audit.reaudit.api must be a JSON object")
    api_config.update(reaudit_api)
    if api_config.get("extra_body", {}).get("thinking", {}).get("type") != "enabled":
        raise ValueError("thinking re-audit requires thinking.type='enabled'")
    workers = int(api_config.get("workers", 1))
    if workers < 1:
        raise ValueError("thinking re-audit workers must be at least 1")

    base_dir = config_path.parent
    paths = config["audit"]["paths"]
    source_dir = resolve_path(paths["source_dir"], base_dir)
    translated_dir = resolve_path(paths["translated_dir"], base_dir)
    uid_file = resolve_path(paths["uid_file"], base_dir)
    audit_dir = resolve_path(paths["output_dir"], base_dir)
    output_dir = resolve_path(
        reaudit["paths"]["output_dir"],
        base_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_verdict = str(reaudit.get("source_verdict", "invalid"))
    uids = [
        line.strip()
        for line in uid_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    items = []
    for index, uid in enumerate(uids, start=1):
        initial_path = audit_dir / "llm_results" / f"{uid}.json"
        if not initial_path.is_file():
            continue
        initial_audit = read_json(initial_path)
        if initial_audit.get("verdict") != selected_verdict:
            continue
        repair_path = audit_dir / "repair_results" / f"{uid}.json"
        items.append(
            {
                "uid": uid,
                "index_1based": index,
                "source": read_json(source_dir / f"{uid}.json"),
                "translated": read_json(translated_dir / f"{uid}.json"),
                "initial_audit": initial_audit,
                "repair": (
                    read_json(repair_path) if repair_path.is_file() else None
                ),
            }
        )

    reuse = bool(reaudit.get("reuse_existing", True)) and not args.no_reuse
    api_key = os.environ.get(
        str(api_config.get("api_key_env", "OPENAI_API_KEY"))
    )

    blind_version = int(reaudit.get("blind_prompt_version", 1))
    blind_results, blind_stats = run_stage(
        items,
        stage="blind",
        prompt_version=blind_version,
        output_dir=output_dir,
        api_key=api_key,
        api_config=api_config,
        reuse=reuse,
        payload_builder=blind_payload,
        prompt_builder=blind_prompt,
        parser=parse_blind_result,
        adjudication=False,
    )

    adjudication_version = int(
        reaudit.get("adjudication_prompt_version", 1)
    )

    def build_adjudication_payload(item: dict) -> dict:
        return adjudication_payload(item, blind_results[item["uid"]])

    adjudication_results, adjudication_stats = run_stage(
        items,
        stage="adjudication",
        prompt_version=adjudication_version,
        output_dir=output_dir,
        api_key=api_key,
        api_config=api_config,
        reuse=reuse,
        payload_builder=build_adjudication_payload,
        prompt_builder=adjudication_prompt,
        parser=parse_adjudication_result,
        adjudication=True,
    )

    records = []
    for item in items:
        uid = item["uid"]
        blind = blind_results[uid]
        adjudication = adjudication_results[uid]
        decision = conservative_decision(
            item,
            blind,
            adjudication,
            threshold,
        )
        records.append(
            {
                "index_1based": item["index_1based"],
                "uid": uid,
                "chinese_query": item["source"].get("nature_language", ""),
                "original_english_query": item["translated"].get(
                    "nature_language", ""
                ),
                "english_oracle_dsl": item["translated"].get(
                    "hard_logic_py", []
                ),
                "repair_status": (item.get("repair") or {}).get(
                    "status", "not_run"
                ),
                "initial_audit": public_result(item["initial_audit"]),
                "blind_review": public_result(blind),
                "adjudication": public_result(adjudication),
                "decision": decision,
            }
        )

    outcome_counts = Counter(
        record["decision"]["outcome"] for record in records
    )
    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_file": str(config_path),
        "model": api_config["model"],
        "endpoint": resolve_chat_completions_url(api_config),
        "thinking": api_config.get("extra_body", {}).get("thinking"),
        "workers": workers,
        "confidence_threshold": threshold,
        "auto_apply": False,
        "summary": {
            "selected": len(records),
            "change_recommended": outcome_counts["change_recommended"],
            "keep_original": outcome_counts["keep_original"],
            "data_conflict": outcome_counts["data_conflict"],
            "source_ambiguous": outcome_counts["source_ambiguous"],
            "manual_review": outcome_counts["manual_review"],
            "blind_stage_failures": blind_stats["failures"],
            "adjudication_stage_failures": adjudication_stats["failures"],
        },
        "blind_stage": blind_stats,
        "adjudication_stage": adjudication_stats,
        "records": records,
    }
    write_outputs(output_dir, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote thinking re-audit to {output_dir}")
    if blind_stats["failures"] or adjudication_stats["failures"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"Thinking re-audit did not complete: {exc}")
        raise SystemExit(2) from None
