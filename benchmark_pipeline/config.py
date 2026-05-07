from __future__ import annotations

"""Configuration helpers for environment loading and default model selection."""

import os

from dotenv import load_dotenv


load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
