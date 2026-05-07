from __future__ import annotations

"""OpenAI client and structured-response helpers used by the agent stages."""

from openai import OpenAI
from pydantic import BaseModel


def get_client() -> OpenAI:
    return OpenAI()


def parse_structured_response(model: str, schema: type[BaseModel], instructions: str, user_input: str) -> BaseModel:
    client = get_client()
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_input},
        ],
        text_format=schema,
    )
    if response.output_parsed is None:
        raise RuntimeError("Model did not return structured output.")
    return response.output_parsed
