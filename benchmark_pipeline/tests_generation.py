from __future__ import annotations

"""JUnit test-suite generation orchestration."""

from pathlib import Path

from benchmark_pipeline.fs_utils import reset_directory, write_artifacts
from benchmark_pipeline.llm import parse_structured_response
from benchmark_pipeline.models import GeneratedTests
from benchmark_pipeline.prompts import build_test_prompt
from benchmark_pipeline.validation import validate_generated_tests


def generate_tests(*, repo_dir: Path, output_dir: Path, model: str) -> GeneratedTests:
    if not repo_dir.exists():
        raise FileNotFoundError(f"Repository not found: {repo_dir}")

    print()
    print("-" * 72)
    print("[tests] Test suite generation")
    print("-" * 72)
    print(f"[tests] Reading baseline repository from {repo_dir.resolve()}")
    print(f"[tests] Requesting generated test suite with model `{model}`")
    parsed = parse_structured_response(
        model=model,
        schema=GeneratedTests,
        instructions=(
            "Generate a JUnit 5 test suite for the provided Java repository. "
            "Return only structured data that matches the schema."
        ),
        user_input=build_test_prompt(repo_dir),
    )
    validate_generated_tests(parsed)

    print(f"[tests] Writing generated tests to {output_dir.resolve()}")
    reset_directory(output_dir)
    write_artifacts(output_dir, parsed.files)
    return parsed
