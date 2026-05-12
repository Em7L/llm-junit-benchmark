from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import _path  # noqa: F401

from benchmark_pipeline.llm import parse_structured_response
from benchmark_pipeline.models import GeneratedTests


class TestLlmStructuredResponse(unittest.TestCase):
    def test_parse_structured_response_returns_parsed_schema_object(self) -> None:
        parsed = GeneratedTests(summary="ok", files=[])
        client = SimpleNamespace(
            responses=SimpleNamespace(parse=Mock(return_value=SimpleNamespace(output_parsed=parsed)))
        )

        with patch("benchmark_pipeline.llm.get_client", return_value=client):
            result = parse_structured_response(
                model="test-model",
                schema=GeneratedTests,
                instructions="system instructions",
                user_input="user prompt",
            )

        self.assertIs(result, parsed)
        client.responses.parse.assert_called_once()
        kwargs = client.responses.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], "test-model")
        self.assertEqual(kwargs["text_format"], GeneratedTests)
        self.assertEqual(kwargs["input"][0]["role"], "system")
        self.assertEqual(kwargs["input"][1]["role"], "user")

    def test_parse_structured_response_rejects_unparsed_model_output(self) -> None:
        client = SimpleNamespace(
            responses=SimpleNamespace(parse=Mock(return_value=SimpleNamespace(output_parsed=None)))
        )

        with patch("benchmark_pipeline.llm.get_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "structured output"):
                parse_structured_response(
                    model="test-model",
                    schema=GeneratedTests,
                    instructions="system instructions",
                    user_input="user prompt",
                )


if __name__ == "__main__":
    unittest.main()
