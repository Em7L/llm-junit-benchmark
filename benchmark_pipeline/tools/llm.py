from __future__ import annotations

"""OpenAI client and structured-response helpers used by the agent stages."""

import os
from openai import OpenAI
from pydantic import BaseModel


def get_client(model: str) -> OpenAI:
    """Returns an OpenAI client configured for the specific model provider."""
    is_deepseek = "deepseek" in model.lower()
    is_gemini = "gemini" in model.lower()
    
    if is_deepseek:
        raw_key = os.getenv("DEEPSEEK_API_KEY")
    elif is_gemini:
        raw_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    else:
        raw_key = os.getenv("OPENAI_API_KEY")
        
    key = raw_key.strip() if raw_key else None

    if not key or "your_" in key:
        provider = "DeepSeek" if is_deepseek else ("Gemini" if is_gemini else "OpenAI")
        raise RuntimeError(f"Missing {provider} API key. Configure the required key in .env.")

    if is_deepseek:
        return OpenAI(
            api_key=key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    elif is_gemini:
        # Force the correct OpenAI-compatibility endpoint even if GEMINI_BASE_URL is set differently
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
        if not base_url.endswith("/openai/"):
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            
        return OpenAI(
            api_key=key,
            base_url=base_url,
        )

    return OpenAI(api_key=key)


def parse_structured_response(
    model: str,
    schema: type[BaseModel],
    instructions: str,
    user_input: str,
) -> BaseModel:
    client = get_client(model)
    is_deepseek = "deepseek" in model.lower()
    is_gemini = "gemini" in model.lower()

    if is_deepseek or is_gemini:
        return _parse_with_fallback(client, model, schema, instructions, user_input)

    try:
        completion = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_input},
            ],
            response_format=schema,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("Model did not return structured output.")
        return parsed
    except Exception as exc:
        message = str(exc)
        if "response_format" in message or "unavailable" in message:
            return _parse_with_fallback(client, model, schema, instructions, user_input)
        raise


def _parse_with_fallback(client: OpenAI, model: str, schema: type[BaseModel], instructions: str, user_input: str) -> BaseModel:
    """Universal fallback: use json_object mode and manual pydantic validation."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": f"{instructions}\n\nYou MUST return valid JSON that matches this schema: {schema.model_json_schema()}"},
            {"role": "user", "content": user_input},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Model returned empty response.")
    return schema.model_validate_json(content)



