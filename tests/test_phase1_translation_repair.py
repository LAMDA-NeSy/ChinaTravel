#!/usr/bin/env python3
"""Regression tests for the Phase 1 translation audit and repair pipeline."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_phase1_translations import (
    audit_dataset,
    load_audit_config,
    merge_llm_results,
    run_llm_audit,
)
from repair_phase1_translations import run_repairs


class FakeResponse:
    def __init__(self, payload: dict):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def source_record(uid: str) -> dict:
    return {
        "uid": uid,
        "start_city": "上海",
        "target_city": "成都",
        "days": 5,
        "people_number": 2,
        "hard_logic_py": [],
        "nature_language": (
            "我们2人，从上海出发，到成都旅行5天，要求如下：\n"
            "希望游览铁像寺水街"
        ),
    }


def translated_record(uid: str, query: str) -> dict:
    return {
        "uid": uid,
        "start_city": "Shanghai",
        "target_city": "Chengdu",
        "days": 5,
        "people_number": 2,
        "hard_logic_py": [],
        "nature_language": query,
    }


class Phase1TranslationRepairTest(unittest.TestCase):
    def test_only_llm_confirmed_invalid_translation_is_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source_dir = root / "zh"
            translated_dir = root / "en"
            output_dir = root / "audit"
            repaired_dir = output_dir / "repaired_data"
            uid_file = root / "uids.txt"
            uids = [
                "uid-valid",
                "uid-invalid",
                "uid-invalid-2",
                "uid-disagreement",
            ]
            uid_file.write_text("\n".join(uids) + "\n", encoding="utf-8")

            complete_query = (
                "We are 2 people traveling from Shanghai to Chengdu for 5 days. "
                "We want to visit Iron Statue Temple Water Street."
            )
            input_queries = {
                "uid-valid": complete_query,
                "uid-invalid": "We are 2 people traveling from Shanghai to",
                "uid-invalid-2": "We are 2 people traveling from Shanghai to",
                "uid-disagreement": "We are 2 people traveling from Shanghai to",
            }
            for uid in uids:
                write_json(source_dir / f"{uid}.json", source_record(uid))
                write_json(
                    translated_dir / f"{uid}.json",
                    translated_record(uid, input_queries[uid]),
                )

            original_bytes = {
                uid: (translated_dir / f"{uid}.json").read_bytes() for uid in uids
            }
            config_path = root / "config.json"
            config = {
                "api": {
                    "base_url": "https://unused.example/v1",
                    "model": "unused",
                },
                "audit": {
                    "paths": {
                        "source_dir": str(source_dir),
                        "translated_dir": str(translated_dir),
                        "uid_file": str(uid_file),
                        "output_dir": str(output_dir),
                        "repaired_dir": str(repaired_dir),
                    },
                    "api": {
                        "provider": "ark_openai_compatible",
                        "base_url": "https://example.invalid/v1",
                        "chat_completions_path": "/chat/completions",
                        "api_key_required": False,
                        "model": "audit-model",
                        "workers": 256,
                        "retries": 1,
                        "timeout_seconds": 120,
                        "temperature": None,
                        "max_tokens": 2048,
                        "extra_body": {
                            "thinking": {"type": "disabled"},
                        },
                        "accepted_finish_reasons": ["stop"],
                    },
                    "enabled": True,
                    "scope": "all",
                    "reuse_existing": False,
                    "prompt_version": 1,
                    "repair": {
                        "enabled": True,
                        "statuses": ["invalid"],
                        "require_llm_invalid": True,
                        "reuse_existing": True,
                        "max_attempts": 1,
                        "verify_with_llm": True,
                        "prompt_version": 1,
                        "api": {},
                    },
                },
            }
            write_json(config_path, config)
            config = load_audit_config(config_path)

            requests = []
            repair_lock = threading.Lock()
            active_repairs = 0
            max_active_repairs = 0

            def fake_urlopen(request, timeout):  # noqa: ANN001
                nonlocal active_repairs, max_active_repairs
                self.assertEqual(timeout, 120)
                self.assertEqual(
                    request.full_url,
                    "https://example.invalid/v1/chat/completions",
                )
                payload = json.loads(request.data.decode("utf-8"))
                requests.append(payload)
                self.assertEqual(
                    payload["model"], "audit-model"
                )
                self.assertEqual(payload["thinking"], {"type": "disabled"})
                self.assertNotIn("do_sample", payload)
                self.assertNotIn("response_format", payload)
                self.assertNotIn("extra_body", payload)
                prompt = payload["messages"][0]["content"]
                if prompt.startswith("You are repairing"):
                    with repair_lock:
                        active_repairs += 1
                        max_active_repairs = max(
                            max_active_repairs, active_repairs
                        )
                    try:
                        time.sleep(0.05)
                        content = json.dumps({"translation": complete_query})
                    finally:
                        with repair_lock:
                            active_repairs -= 1
                else:
                    is_original_invalid = (
                        (
                            '"uid": "uid-invalid"' in prompt
                            or '"uid": "uid-invalid-2"' in prompt
                        )
                        and '"english_query": "We are 2 people traveling '
                        'from Shanghai to"' in prompt
                    )
                    verdict = "invalid" if is_original_invalid else "pass"
                    content = json.dumps(
                        {
                            "verdict": verdict,
                            "issue_codes": (
                                ["truncated_query"] if verdict == "invalid" else []
                            ),
                            "missing_or_changed_information": (
                                ["destination and requirements"]
                                if verdict == "invalid"
                                else []
                            ),
                            "explanation": "mock audit",
                            "confidence": 1.0,
                        }
                    )
                return FakeResponse(
                    {
                        "model": "audit-model",
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"content": content},
                            }
                        ],
                        "usage": {},
                    }
                )

            report, all_records = audit_dataset(
                source_dir, translated_dir, uid_file
            )
            with patch(
                "urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                llm_results, llm_stats = run_llm_audit(
                    all_records,
                    source_dir=source_dir,
                    translated_dir=translated_dir,
                    output_dir=output_dir,
                    config=config,
                    force_no_reuse=False,
                )
                report = merge_llm_results(
                    report, all_records, llm_results, llm_stats
                )
                stats = run_repairs(
                    report,
                    source_dir=source_dir,
                    translated_dir=translated_dir,
                    repaired_dir=repaired_dir,
                    uid_file=uid_file,
                    output_dir=output_dir,
                    config=config,
                    force_no_reuse=False,
                )

            self.assertEqual(stats["workers"], 256)
            self.assertEqual(stats["candidates"], 2)
            self.assertEqual(stats["repaired"], 2)
            self.assertEqual(stats["untouched"], 2)
            self.assertEqual(
                stats["skipped_not_llm_confirmed"], ["uid-disagreement"]
            )
            self.assertEqual(len(requests), 8)
            self.assertGreaterEqual(max_active_repairs, 2)
            repair_prompts = [
                request["messages"][0]["content"]
                for request in requests
                if request["messages"][0]["content"].startswith(
                    "You are repairing"
                )
            ]
            self.assertEqual(len(repair_prompts), 2)
            self.assertEqual(
                {
                    uid
                    for uid in ("uid-invalid", "uid-invalid-2")
                    if any(f'"uid": "{uid}"' in prompt for prompt in repair_prompts)
                },
                {"uid-invalid", "uid-invalid-2"},
            )

            for uid in uids:
                self.assertEqual(
                    (translated_dir / f"{uid}.json").read_bytes(),
                    original_bytes[uid],
                )
            self.assertEqual(
                (repaired_dir / "uid-valid.json").read_bytes(),
                original_bytes["uid-valid"],
            )
            self.assertEqual(
                (repaired_dir / "uid-disagreement.json").read_bytes(),
                original_bytes["uid-disagreement"],
            )
            for uid in ("uid-invalid", "uid-invalid-2"):
                repaired = json.loads(
                    (repaired_dir / f"{uid}.json").read_text(encoding="utf-8")
                )
                self.assertEqual(repaired["nature_language"], complete_query)

            repair_log = json.loads(
                (output_dir / "translation_repairs.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                [record["uid"] for record in repair_log["records"]],
                ["uid-invalid", "uid-invalid-2"],
            )
            self.assertEqual(repair_log["records"][0]["status"], "repaired")
            self.assertEqual(repair_log["records"][1]["status"], "repaired")

            with patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("cached repairs must not call the API"),
            ):
                cached_stats = run_repairs(
                    report,
                    source_dir=source_dir,
                    translated_dir=translated_dir,
                    repaired_dir=repaired_dir,
                    uid_file=uid_file,
                    output_dir=output_dir,
                    config=config,
                    force_no_reuse=False,
                )
            self.assertEqual(cached_stats["cached_repairs"], 2)
            self.assertEqual(cached_stats["repaired"], 2)


if __name__ == "__main__":
    unittest.main()
