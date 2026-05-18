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
                model="gpt-5.4-mini",
                schema=GeneratedTests,
                instructions="system instructions",
                user_input="user prompt",
            )

        self.assertIs(result, parsed)
        client.beta.chat.completions.parse.assert_called_once()
        kwargs = client.beta.chat.completions.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5.4-mini")
        self.assertEqual(kwargs["response_format"], GeneratedTests)
        self.assertEqual(kwargs["messages"][0]["role"], "system")
        self.assertEqual(kwargs["messages"][1]["role"], "user")
        self.assertEqual(kwargs["reasoning_effort"], "low")

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

    def test_parse_structured_response_falls_back_when_native_parse_is_unavailable(self) -> None:
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"summary":"ok","files":[],"assumptions":[],"repair_attempts":0,"repair_outcome":"repair_not_needed","repair_reasons":[]}'
                    )
                )
            ]
        )
        client = SimpleNamespace(
            beta=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(parse=Mock(side_effect=RuntimeError("response_format unavailable")))
                )
            ),
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=response))
            ),
        )

        with patch("benchmark_pipeline.tools.llm.get_client", return_value=client):
            result = parse_structured_response(
                model="gpt-5.4-mini",
                schema=GeneratedTests,
                instructions="system instructions",
                user_input="user prompt",
            )

        self.assertIsInstance(result, GeneratedTests)
        self.assertEqual(result.summary, "ok")
        client.chat.completions.create.assert_called_once()
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5.4-mini")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertIn("matches this schema", kwargs["messages"][0]["content"])
        self.assertEqual(kwargs["reasoning_effort"], "low")

    def test_deepseek_model_uses_fallback_json_parsing(self) -> None:
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"summary":"ok","files":[],"assumptions":[],"repair_attempts":0,"repair_outcome":"repair_not_needed","repair_reasons":[]}'
                    )
                )
            ]
        )
        client = SimpleNamespace(
            beta=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(parse=Mock())
                )
            ),
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=response))
            ),
        )

        with patch("benchmark_pipeline.tools.llm.get_client", return_value=client):
            result = parse_structured_response(
                model="deepseek-v4-flash",
                schema=GeneratedTests,
                instructions="system instructions",
                user_input="user prompt",
            )

        self.assertIsInstance(result, GeneratedTests)
        self.assertEqual(result.summary, "ok")
        client.beta.chat.completions.parse.assert_not_called()
        client.chat.completions.create.assert_called_once()
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "deepseek-v4-flash")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertIn("matches this schema", kwargs["messages"][0]["content"])
        self.assertEqual(kwargs["reasoning_effort"], "low")
        self.assertEqual(kwargs["extra_body"], {"thinking": {"type": "enabled"}})


if __name__ == "__main__":
    unittest.main()
