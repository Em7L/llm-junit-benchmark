from __future__ import annotations

"""CLI entrypoint for generating JUnit tests for the baseline repository with Agent 2."""

import argparse
from pathlib import Path

from benchmark_pipeline.config import TEST_GEN_MODEL
from benchmark_pipeline.fs_utils import dump_json
from benchmark_pipeline.tests_generation import generate_tests


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a JUnit 5 test suite with Agent 2.")
    parser.add_argument("--repo-dir", default="artifacts/baseline_repo", help="Path to the baseline repository.")
    parser.add_argument("--output-dir", default="artifacts/generated_tests", help="Directory to write generated test files into.")
    parser.add_argument("--model", default=TEST_GEN_MODEL, help="Model for Agent 2.")

    parser.add_argument("--manifest", default="artifacts/manifests/generated_tests.json", help="Where to store the structured response.")
    args = parser.parse_args()

    parsed = generate_tests(
        repo_dir=Path(args.repo_dir),
        output_dir=Path(args.output_dir),
        model=args.model,
    )
    print(f"[tests] Writing manifest to {Path(args.manifest).resolve()}")
    dump_json(Path(args.manifest), parsed.model_dump())
    print()
    print(f"Generated test suite at {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
