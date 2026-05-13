from __future__ import annotations

"""Configuration helpers for environment loading and default model selection."""

import os

from dotenv import load_dotenv


load_dotenv()

# Model for Agent 1 (baseline repo generation).
REPO_GEN_MODEL = os.getenv("REPO_GEN_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.4-mini"))

# Model for Agent 2 (JUnit test suite generation).
TEST_GEN_MODEL = os.getenv("TEST_GEN_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o"))
