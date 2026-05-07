from __future__ import annotations

"""CLI entrypoint for generating mutant repositories from the baseline project with Agent 3."""

import argparse
from pathlib import Path

from benchmark_pipeline.config import DEFAULT_MODEL
from benchmark_pipeline.fs_utils import copy_tree_into, dump_json, reset_directory, write_artifacts
from benchmark_pipeline.llm import parse_structured_response
from benchmark_pipeline.models import GeneratedMutants
from benchmark_pipeline.prompts import build_mutation_prompt


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate buggy mutants with Agent 3.")
    parser.add_argument("--repo-dir", default="artifacts/baseline_repo", help="Path to the baseline repository.")
    parser.add_argument("--output-dir", default="artifacts/mutants", help="Directory to write mutant repositories into.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model for Agent 3.")
    parser.add_argument("--count", type=int, default=5, help="Number of single-bug mutants to generate.")
    parser.add_argument("--manifest", default="artifacts/manifests/generated_mutants.json", help="Where to store the structured response.")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir)
    if not repo_dir.exists():
        raise FileNotFoundError(f"Repository not found: {repo_dir}")

    parsed = parse_structured_response(
        model=args.model,
        schema=GeneratedMutants,
        instructions=(
            "You are Agent 3. Generate realistic single-bug mutants for the provided Java repository. "
            "Return only structured data that matches the schema."
        ),
        user_input=build_mutation_prompt(repo_dir, args.count),
    )

    output_dir = Path(args.output_dir)
    reset_directory(output_dir)

    for mutant in parsed.mutants:
        mutant_dir = output_dir / mutant.mutant_id
        reset_directory(mutant_dir)
        copy_tree_into(repo_dir, mutant_dir)
        write_artifacts(mutant_dir, mutant.changed_files)

    dump_json(Path(args.manifest), parsed.model_dump())
    print(f"Generated {len(parsed.mutants)} mutants at {output_dir.resolve()}")


if __name__ == "__main__":
    main()
