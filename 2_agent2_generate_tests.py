from __future__ import annotations

import argparse
from pathlib import Path

from pipeline_common import (
    DEFAULT_MODEL,
    GeneratedTests,
    build_test_prompt,
    dump_json,
    parse_response,
    reset_directory,
    write_artifacts,
)


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

    parsed = parse_response(
        model=args.model,
        schema=GeneratedTests,
        instructions=(
            "You are Agent 2. Generate a JUnit 5 test suite for the provided Java repository. "
            "Return only structured data that matches the schema."
        ),
        user_input=build_test_prompt(repo_dir),
    )

    output_dir = Path(args.output_dir)
    reset_directory(output_dir)
    write_artifacts(output_dir, parsed.files)
    dump_json(Path(args.manifest), parsed.model_dump())
    print(f"Generated test suite at {output_dir.resolve()}")


if __name__ == "__main__":
    main()
