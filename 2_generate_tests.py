from __future__ import annotations

"""CLI entrypoint for generating JUnit tests for the baseline repository with Agent 2."""

import argparse
from pathlib import Path

from benchmark_pipeline.config import DEFAULT_MODEL
from benchmark_pipeline.fs_utils import dump_json, reset_directory, write_artifacts
from benchmark_pipeline.llm import parse_structured_response
from benchmark_pipeline.models import GeneratedTests
from benchmark_pipeline.prompts import build_test_prompt
from benchmark_pipeline.validation import validate_generated_tests


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a JUnit 5 test suite with Agent 2.")
    parser.add_argument("--repo-dir", default="artifacts/baseline_repo", help="Path to the baseline repository.")
    parser.add_argument("--output-dir", default="artifacts/generated_tests", help="Directory to write generated test files into.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model for Agent 2.")
    parser.add_argument("--manifest", default="artifacts/manifests/generated_tests.json", help="Where to store the structured response.")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir)
    if not repo_dir.exists():
        raise FileNotFoundError(f"Repository not found: {repo_dir}")

    print(f"[tests] Reading baseline repository from {repo_dir.resolve()}")
    print(f"[tests] Requesting generated test suite with model `{args.model}`")
    parsed = parse_structured_response(
        model=args.model,
        schema=GeneratedTests,
        instructions=(
            "Generate a JUnit 5 test suite for the provided Java repository. "
            "Return only structured data that matches the schema."
        ),
        user_input=build_test_prompt(repo_dir),
    )
    validate_generated_tests(parsed)

    output_dir = Path(args.output_dir)
    print(f"[tests] Writing generated tests to {output_dir.resolve()}")
    reset_directory(output_dir)
    write_artifacts(output_dir, parsed.files)
    print(f"[tests] Writing manifest to {Path(args.manifest).resolve()}")
    dump_json(Path(args.manifest), parsed.model_dump())
    print(f"Generated test suite at {output_dir.resolve()}")


if __name__ == "__main__":
    main()
