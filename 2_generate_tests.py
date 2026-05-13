from __future__ import annotations

"""CLI entrypoint for generating JUnit tests for the baseline repository with Agent 2."""

import argparse
from pathlib import Path

from benchmark_pipeline.config import TEST_GEN_MODEL
from benchmark_pipeline.generation.runner import TestGenerationConfig, run_test_generation


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a JUnit 5 test suite with Agent 2.")
    parser.add_argument("--repo-dir", default="artifacts/baseline_repo", help="Path to the baseline repository.")
    parser.add_argument("--output-dir", default="artifacts/generated_tests", help="Directory to write generated test files into.")
    parser.add_argument("--model", default=TEST_GEN_MODEL, help="Model for Agent 2.")

    parser.add_argument("--manifest", default="artifacts/manifests/generated_tests.json", help="Where to store the structured response.")
    parser.add_argument("--max-repairs", type=int, default=2, help="Maximum number of repair attempts after the initial test generation.")
    args = parser.parse_args()

    run_test_generation(
        TestGenerationConfig(
            repo_dir=Path(args.repo_dir),
            output_dir=Path(args.output_dir),
            model=args.model,
            manifest_path=Path(args.manifest),
            max_repairs=args.max_repairs,
        )
    )


if __name__ == "__main__":
    main()
