from __future__ import annotations

import argparse
from pathlib import Path

from pipeline_common import (
    DEFAULT_MODEL,
    GeneratedRepo,
    build_repo_prompt,
    dump_json,
    parse_response,
    reset_directory,
    write_artifacts,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a baseline Maven/JDK21 repository with Agent 1.")
    parser.add_argument("--output-dir", default="artifacts/baseline_repo", help="Directory to write the generated repository into.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model for Agent 1.")
    parser.add_argument("--project-name", default="generated-java-app", help="Suggested project name.")
    parser.add_argument("--manifest", default="artifacts/manifests/baseline_repo.json", help="Where to store the structured response.")
    args = parser.parse_args()

    parsed = parse_response(
        model=args.model,
        schema=GeneratedRepo,
        instructions=(
            "You are Agent 1. Generate a baseline Java Maven repository. "
            "Return only structured data that matches the schema."
        ),
        user_input=build_repo_prompt(args.project_name),
    )

    output_dir = Path(args.output_dir)
    reset_directory(output_dir)
    write_artifacts(output_dir, parsed.files)
    dump_json(Path(args.manifest), parsed.model_dump())
    print(f"Generated baseline repository at {output_dir.resolve()}")


if __name__ == "__main__":
    main()
