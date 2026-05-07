from __future__ import annotations

"""CLI entrypoint for generating the baseline Maven repository with Agent 1."""

import argparse
from pathlib import Path

from benchmark_pipeline.config import DEFAULT_MODEL
from benchmark_pipeline.fs_utils import dump_json, reset_directory, write_artifacts
from benchmark_pipeline.llm import parse_structured_response
from benchmark_pipeline.maven import run_maven_tests
from benchmark_pipeline.models import GeneratedRepo
from benchmark_pipeline.prompts import build_repo_prompt, build_repo_repair_prompt
from benchmark_pipeline.validation import OutputValidationError, validate_generated_repo


def generate_verified_repo(
    *,
    model: str,
    project_name: str,
    output_dir: Path,
    max_repairs: int,
    verify_cmd: list[str],
) -> GeneratedRepo:
    print()
    print(f"[baseline] Requesting initial repository generation with model `{model}`")
    parsed = parse_structured_response(
        model=model,
        schema=GeneratedRepo,
        instructions=(
            "Generate a complete baseline Java Maven repository that satisfies the requirements. "
            "Return only structured data that matches the schema."
        ),
        user_input=build_repo_prompt(project_name),
    )

    for attempt in range(max_repairs + 1):
        print()
        print(f"[baseline] Candidate attempt {attempt + 1}/{max_repairs + 1}")
        try:
            validate_generated_repo(parsed)
        except OutputValidationError as exc:
            if attempt == max_repairs:
                raise RuntimeError(
                    "Generated repository failed semantic validation after repair attempts.\n"
                    f"{exc}"
                ) from exc

            print(
                f"[baseline] Validation failed ({exc}). "
                f"Requesting repair attempt {attempt + 1}/{max_repairs}"
            )
            parsed = parse_structured_response(
                model=model,
                schema=GeneratedRepo,
                instructions=(
                    "Repair the Java Maven repository so it matches the expected Maven project structure "
                    "and passes verification. Return only structured data that matches the schema."
                ),
                user_input=build_repo_repair_prompt(
                    repo_root=output_dir,
                    project_name=project_name,
                    build_output=str(exc),
                ),
            )
            continue

        print(f"[baseline] Writing candidate repository to {output_dir}")
        reset_directory(output_dir)
        write_artifacts(output_dir, parsed.files)
        print(f"[baseline] Verifying repository with: {' '.join(verify_cmd)}")
        result = run_maven_tests(output_dir, verify_cmd)
        if result.passed:
            print("[baseline] Verification passed")
            return parsed

        if attempt == max_repairs:
            print("[baseline] Verification failed and no repair attempts remain")
            raise RuntimeError(
                "Generated repository failed verification after repair attempts.\n"
                f"Exit code: {result.exit_code}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )

        print(
            f"[baseline] Verification failed "
            f"(exit={result.exit_code}, failures={result.failures}, errors={result.errors}). "
            f"Requesting repair attempt {attempt + 1}/{max_repairs}"
        )
        parsed = parse_structured_response(
            model=model,
            schema=GeneratedRepo,
            instructions=(
                "Repair the Java Maven repository so it compiles and passes verification. "
                "Return only structured data that matches the schema."
            ),
            user_input=build_repo_repair_prompt(
                repo_root=output_dir,
                project_name=project_name,
                build_output=f"{result.stdout}\n{result.stderr}".strip(),
            ),
        )

    raise RuntimeError("Unreachable repository generation state.")


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
