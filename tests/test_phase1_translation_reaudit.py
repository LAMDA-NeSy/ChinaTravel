#!/usr/bin/env python3
"""Regression tests for conservative thinking-enabled Phase 1 re-audit."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import reaudit_phase1_translations as reaudit


class FakeResponse:
    def __init__(self, data: dict):
        self.body = json.dumps(data).encode("utf-8")

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


class Phase1TranslationReauditTest(unittest.TestCase):
    def test_conservative_two_stage_decisions_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source_dir = root / "zh"
            translated_dir = root / "en"
            audit_dir = root / "audit"
            repaired_dir = audit_dir / "repaired_data"
            output_dir = audit_dir / "thinking_reaudit"
            uid_file = root / "uids.txt"
            uids = [
                "uid-error",
                "uid-acceptable",
                "uid-conflict",
                "uid-disagreement",
            ]
            uid_file.write_text("\n".join(uids) + "\n", encoding="utf-8")

            original_bytes = {}
            for uid in uids:
                source = {
                    "uid": uid,
                    "start_city": "上海",
                    "target_city": "成都",
                    "days": 2,
                    "people_number": 1,
                    "hard_logic_py": ["result=(day_count(plan)==2)"],
                    "nature_language": f"{uid} 中文查询",
                }
                translated = {
                    "uid": uid,
                    "start_city": "Shanghai",
                    "target_city": "Chengdu",
                    "days": 2,
                    "people_number": 1,
                    "hard_logic_py": ["result=(day_count(plan)==2)"],
                    "nature_language": f"{uid} original English query",
                }
                write_json(source_dir / f"{uid}.json", source)
                write_json(translated_dir / f"{uid}.json", translated)
                original_bytes[uid] = (
                    translated_dir / f"{uid}.json"
                ).read_bytes()
                write_json(
                    audit_dir / "llm_results" / f"{uid}.json",
                    {
                        "uid": uid,
                        "verdict": "invalid",
                        "explanation": "initial mock invalid",
                        "confidence": 0.95,
                    },
                )

            repaired_translation = "uid-error complete repaired English query"
            write_json(
                audit_dir / "repair_results" / "uid-error.json",
                {
                    "uid": "uid-error",
                    "status": "repaired",
                    "original_translation": (
                        "uid-error original English query"
                    ),
                    "repaired_translation": repaired_translation,
                    "attempts": [],
                },
            )
            config_path = root / "config.json"
            write_json(
                config_path,
                {
                    "api": {
                        "base_url": "https://unused.example/v1",
                        "model": "unused",
                    },
                    "audit": {
                        "paths": {
                            "source_dir": str(source_dir),
                            "translated_dir": str(translated_dir),
                            "uid_file": str(uid_file),
                            "output_dir": str(audit_dir),
                            "repaired_dir": str(repaired_dir),
                        },
                        "api": {
                            "provider": "ark_openai_compatible",
                            "base_url": (
                                "https://example.invalid/v1"
                            ),
                            "chat_completions_path": "/chat/completions",
                            "api_key_env": "OPENAI_API_KEY",
                            "api_key_required": True,
                            "model": "audit-model",
                            "workers": 256,
                            "retries": 1,
                            "timeout_seconds": 120,
                            "temperature": None,
                            "max_tokens": 2048,
                            "extra_body": {
                                "thinking": {"type": "disabled"}
                            },
                            "accepted_finish_reasons": ["stop"],
                        },
                        "repair": {
                            "enabled": False,
                            "statuses": ["invalid"],
                        },
                        "reaudit": {
                            "enabled": True,
                            "source_verdict": "invalid",
                            "reuse_existing": True,
                            "confidence_threshold": 0.9,
                            "auto_apply": False,
                            "blind_prompt_version": 1,
                            "adjudication_prompt_version": 1,
                            "paths": {"output_dir": str(output_dir)},
                            "api": {
                                "workers": 256,
                                "max_tokens": 4096,
                                "extra_body": {
                                    "thinking": {"type": "enabled"}
                                },
                            },
                        },
                    },
                },
            )

            requests = []

            def uid_from_prompt(prompt: str) -> str:
                for uid in uids:
                    if f'"uid": "{uid}"' in prompt:
                        return uid
                raise AssertionError("mock request has no known UID")

            def fake_urlopen(request, timeout):  # noqa: ANN001
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
                self.assertEqual(payload["thinking"], {"type": "enabled"})
                self.assertNotIn("extra_body", payload)
                self.assertEqual(
                    request.get_header("Authorization"), "Bearer test-key"
                )
                prompt = payload["messages"][0]["content"]
                uid = uid_from_prompt(prompt)
                if prompt.startswith("You are the first independent reviewer"):
                    blind_results = {
                        "uid-error": ("translation_error", 0.97),
                        "uid-acceptable": ("acceptable", 0.98),
                        "uid-conflict": ("data_conflict", 0.96),
                        "uid-disagreement": ("translation_error", 0.96),
                    }
                    verdict, confidence = blind_results[uid]
                    content = {
                        "verdict": verdict,
                        "issue_codes": [],
                        "material_differences": [],
                        "explanation": f"blind {verdict}",
                        "confidence": confidence,
                    }
                else:
                    adjudication_results = {
                        "uid-error": {
                            "verdict": "translation_error",
                            "recommended_action": "use_repaired",
                            "change_necessary": True,
                            "recommended_translation": repaired_translation,
                            "confidence": 0.98,
                        },
                        "uid-acceptable": {
                            "verdict": "acceptable",
                            "recommended_action": "keep_original",
                            "change_necessary": False,
                            "recommended_translation": "",
                            "confidence": 0.99,
                        },
                        "uid-conflict": {
                            "verdict": "data_conflict",
                            "recommended_action": (
                                "fix_dictionary_or_oracle"
                            ),
                            "change_necessary": False,
                            "recommended_translation": "",
                            "confidence": 0.98,
                        },
                        "uid-disagreement": {
                            "verdict": "needs_review",
                            "recommended_action": "manual_review",
                            "change_necessary": False,
                            "recommended_translation": "",
                            "confidence": 0.7,
                        },
                    }
                    content = {
                        **adjudication_results[uid],
                        "issue_codes": [],
                        "material_differences": [],
                        "explanation": f"adjudication for {uid}",
                    }
                return FakeResponse(
                    {
                        "model": "audit-model",
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {
                                    "content": json.dumps(content)
                                },
                            }
                        ],
                        "usage": {},
                    }
                )

            arguments = argparse.Namespace(
                config=config_path,
                no_reuse=False,
            )
            with (
                patch.object(reaudit, "parse_args", return_value=arguments),
                patch("urllib.request.urlopen", side_effect=fake_urlopen),
                patch.dict(
                    os.environ,
                    {"OPENAI_API_KEY": "test-key"},
                ),
            ):
                self.assertEqual(reaudit.main(), 0)

            self.assertEqual(len(requests), 8)
            report = read_json(output_dir / "phase1_thinking_reaudit.json")
            self.assertEqual(
                report["summary"],
                {
                    "selected": 4,
                    "change_recommended": 1,
                    "keep_original": 1,
                    "data_conflict": 1,
                    "source_ambiguous": 0,
                    "manual_review": 1,
                    "blind_stage_failures": 0,
                    "adjudication_stage_failures": 0,
                },
            )
            decisions = {
                record["uid"]: record["decision"]["outcome"]
                for record in report["records"]
            }
            self.assertEqual(decisions["uid-error"], "change_recommended")
            self.assertEqual(decisions["uid-acceptable"], "keep_original")
            self.assertEqual(decisions["uid-conflict"], "data_conflict")
            self.assertEqual(decisions["uid-disagreement"], "manual_review")

            for uid in uids:
                self.assertEqual(
                    (translated_dir / f"{uid}.json").read_bytes(),
                    original_bytes[uid],
                )

            with (
                patch.object(reaudit, "parse_args", return_value=arguments),
                patch(
                    "urllib.request.urlopen",
                    side_effect=AssertionError(
                        "cached re-audit must not call the API"
                    ),
                ),
                patch.dict(os.environ, {"OPENAI_API_KEY": ""}),
            ):
                self.assertEqual(reaudit.main(), 0)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
