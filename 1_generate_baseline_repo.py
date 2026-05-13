from __future__ import annotations

"""CLI entrypoint for generating the baseline Maven repository with Agent 1."""

import argparse
from pathlib import Path

from benchmark_pipeline.config import REPO_GEN_MODEL
from benchmark_pipeline.generation.runner import BaselineGenerationConfig, run_baseline_generation


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a baseline Maven/JDK21 repository with Agent 1.")
    parser.add_argument("--output-dir", default="artifacts/baseline_repo", help="Directory to write the generated repository into.")
    parser.add_argument("--model", default=REPO_GEN_MODEL, help="Model for Agent 1.")

    parser.add_argument("--project-name", default="generated-java-app", help="Suggested project name.")
    parser.add_argument("--manifest", default="artifacts/manifests/baseline_repo.json", help="Where to store the structured response.")
    parser.add_argument("--verify-cmd", nargs="+", default=["mvn", "test"], help="Command used to verify the generated repository.")
    parser.add_argument("--max-repairs", type=int, default=2, help="Maximum number of repair attempts after the initial generation.")
    args = parser.parse_args()

    run_baseline_generation(
        BaselineGenerationConfig(
            model=args.model,
            project_name=args.project_name,
            output_dir=Path(args.output_dir),
            manifest_path=Path(args.manifest),
            verify_cmd=args.verify_cmd,
            max_repairs=args.max_repairs,
        )
    )


if __name__ == "__main__":
    main()
