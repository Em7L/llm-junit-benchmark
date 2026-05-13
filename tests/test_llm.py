from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import _path  # noqa: F401

from benchmark_pipeline.tools.llm import parse_structured_response
from benchmark_pipeline.models import GeneratedTests


class TestLlmStructuredResponse(unittest.TestCase):
    def test_parse_structured_response_returns_parsed_schema_object(self) -> None:
        parsed = GeneratedTests(summary="ok", files=[])
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(parsed=parsed),
                )
            ]
        )
        client = SimpleNamespace(
            beta=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(parse=Mock(return_value=completion))
                )
            )
        )

        with patch("benchmark_pipeline.tools.llm.get_client", return_value=client):
            result = parse_structured_response(
                model="test-model",
                schema=GeneratedTests,
                instructions="system instructions",
                user_input="user prompt",
            )

        self.assertIs(result, parsed)
        client.beta.chat.completions.parse.assert_called_once()
        kwargs = client.beta.chat.completions.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], "test-model")
        self.assertEqual(kwargs["response_format"], GeneratedTests)
        self.assertEqual(kwargs["messages"][0]["role"], "system")
        self.assertEqual(kwargs["messages"][1]["role"], "user")

    def test_parse_structured_response_rejects_unparsed_model_output(self) -> None:
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(parsed=None),
                )
            ]
        )
        client = SimpleNamespace(
            beta=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(parse=Mock(return_value=completion))
                )
            )
        )

        with patch("benchmark_pipeline.tools.llm.get_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "structured output"):
                parse_structured_response(
                    model="test-model",
                    schema=GeneratedTests,
                    instructions="system instructions",
                    user_input="user prompt",
                )


if __name__ == "__main__":
    unittest.main()
