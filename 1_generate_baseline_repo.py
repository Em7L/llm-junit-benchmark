from __future__ import annotations

"""CLI entrypoint for generating the baseline Maven repository with Agent 1."""

import argparse
from pathlib import Path

from benchmark_pipeline.config import DEFAULT_MODEL
from benchmark_pipeline.fs_utils import dump_json
from benchmark_pipeline.repo_generation import generate_verified_repo


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a baseline Maven/JDK21 repository with Agent 1.")
    parser.add_argument("--output-dir", default="artifacts/baseline_repo", help="Directory to write the generated repository into.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model for Agent 1.")
    parser.add_argument("--project-name", default="generated-java-app", help="Suggested project name.")
    parser.add_argument("--manifest", default="artifacts/manifests/baseline_repo.json", help="Where to store the structured response.")
    parser.add_argument("--verify-cmd", nargs="+", default=["mvn", "test"], help="Command used to verify the generated repository.")
    parser.add_argument("--max-repairs", type=int, default=2, help="Maximum number of repair attempts after the initial generation.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    print()
    print("-" * 72)
    print("[baseline] Baseline repository generation")
    print("-" * 72)
    print(f"[baseline] Output directory: {output_dir.resolve()}")
    parsed = generate_verified_repo(
        model=args.model,
        project_name=args.project_name,
        output_dir=output_dir,
        max_repairs=args.max_repairs,
        verify_cmd=args.verify_cmd,
    )
    print(f"[baseline] Writing manifest to {Path(args.manifest).resolve()}")
    dump_json(Path(args.manifest), parsed.model_dump())
    print()
    print(f"Generated baseline repository at {output_dir.resolve()}")


if __name__ == "__main__":
    main()
