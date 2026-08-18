#!/usr/bin/env python3
"""Regression tests for agent tool protocols and OpenAI wire formats."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from agent_env.adapter import ChinaTravelEnvAdapter
from agent_env.runtime import AgentToolRuntime
from chinatravel.agent.llms import OpenAICompatibleLLM
from chinatravel.environment.world_env import WorldEnv


class _Attractions:
    def select(self, city, key, predicate):
        values = ["Shanghai Museum", "Yu Garden", 12345]
        return [value for value in values if predicate(value)]


class _PagedAttractions:
    def select(self, city, key, predicate):
        return pd.DataFrame(
            [{"name": "Museum {}".format(index)} for index in range(15)]
        )


class AgentToolProtocolTests(unittest.TestCase):
    def test_runtime_lists_mcp_chat_and_responses_tool_schemas(self):
        runtime = AgentToolRuntime()

        mcp_tools = runtime.list_mcp_tools()
        chat_tools = runtime.list_openai_tools()
        responses_tools = runtime.list_openai_responses_tools()

        self.assertGreater(len(mcp_tools), 0)
        self.assertEqual(len(mcp_tools), len(chat_tools))
        self.assertEqual(len(mcp_tools), len(responses_tools))
        self.assertIn("inputSchema", mcp_tools[0])
        self.assertEqual(chat_tools[0]["type"], "function")
        self.assertIn("function", chat_tools[0])
        self.assertEqual(responses_tools[0]["type"], "function")
        self.assertNotIn("function", responses_tools[0])
        self.assertIn("parameters", responses_tools[0])

    def test_runtime_self_check_passes(self):
        result = AgentToolRuntime().self_check()

        self.assertTrue(result["success"], result)

    def test_contains_uses_direct_structured_predicate(self):
        adapter = ChinaTravelEnvAdapter(lang="en")
        adapter._env = SimpleNamespace(attractions=_Attractions())

        text_result = adapter.call_tool(
            "attractions_select",
            {
                "city": "Shanghai",
                "key": "name",
                "op": "contains",
                "value": "Museum",
            },
        )
        numeric_result = adapter.call_tool(
            "attractions_select",
            {
                "city": "Shanghai",
                "key": "name",
                "op": "contains",
                "value": 234,
            },
        )

        self.assertTrue(text_result["success"])
        self.assertEqual(text_result["data"], ["Shanghai Museum"])
        self.assertTrue(numeric_result["success"])
        self.assertEqual(numeric_result["data"], [12345])

    def test_structured_calls_preserve_next_page_history(self):
        env = WorldEnv.__new__(WorldEnv)
        env.results = []
        env.attractions = _PagedAttractions()
        adapter = ChinaTravelEnvAdapter(lang="en")
        adapter._env = env

        first = adapter.call_tool(
            "attractions_select",
            {
                "city": "Shanghai",
                "key": "name",
                "op": "contains",
                "value": "Museum",
            },
        )
        second = adapter.call_tool("next_page", {})

        self.assertTrue(first["success"])
        self.assertEqual(first["data"]["row_count"], 10)
        self.assertEqual(first["data"]["rows"][0]["name"], "Museum 0")
        self.assertTrue(second["success"])
        self.assertEqual(second["data"]["row_count"], 5)
        self.assertEqual(second["data"]["rows"][0]["name"], "Museum 10")


class ResponsesWireFormatTests(unittest.TestCase):
    def test_one_line_does_not_send_unsupported_stop_to_responses_api(self):
        create = Mock(
            return_value={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "first\nsecond"}],
                    }
                ]
            }
        )
        llm = OpenAICompatibleLLM(
            "test-model",
            api_key="test-key",
            wire_api="responses",
        )
        llm._llm = SimpleNamespace(responses=SimpleNamespace(create=create))

        result = llm([{"role": "user", "content": "test"}])

        self.assertEqual(result, "first")
        self.assertNotIn("stop", create.call_args.kwargs)
        self.assertEqual(create.call_args.kwargs["max_output_tokens"], 4096)


if __name__ == "__main__":
    unittest.main()
