from __future__ import annotations

"""Configuration helpers for environment loading and default model selection."""

import os

from dotenv import load_dotenv


load_dotenv()

# Model for Agent 1 (Baseline Repo Generation)
REPO_GEN_MODEL = os.getenv("REPO_GEN_MODEL", "deepseek-v4-flash")

# Model for Agent 2 (JUnit Test Suite Generation)
TEST_GEN_MODEL = os.getenv("TEST_GEN_MODEL", "gpt-4o")

# List of models to benchmark for test generation
TEST_MODELS_LIST = ["gpt-4o", "gpt-5.4-mini", "gpt-4o-mini"]



