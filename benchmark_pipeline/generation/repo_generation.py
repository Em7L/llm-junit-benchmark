from __future__ import annotations

"""Baseline Maven repository generation and verification."""

from pathlib import Path

from benchmark_pipeline.fs_utils import reset_directory, write_artifacts
from benchmark_pipeline.generation.profiles import BenchmarkProfile
from benchmark_pipeline.tools.llm import parse_structured_response
from benchmark_pipeline.tools.maven import run_maven_tests
from benchmark_pipeline.models import GeneratedRepo
from benchmark_pipeline.generation.prompts import build_repo_prompt, build_repo_repair_prompt
from benchmark_pipeline.generation.validation import OutputValidationError, validate_generated_repo


def generate_verified_repo(
    *,
    model: str,
    project_name: str,
    output_dir: Path,
    max_repairs: int,
    verify_cmd: list[str],
    benchmark_profile: BenchmarkProfile | None = None,
) -> GeneratedRepo:
    print(f"[baseline] model={model}")
    print("[baseline] requesting initial repository generation")
    parsed = parse_structured_response(
        model=model,
        schema=GeneratedRepo,
        instructions=(
            "Generate a complete baseline Java Maven repository that satisfies the requirements. "
            "Return only structured data that matches the schema."
        ),
        user_input=build_repo_prompt(project_name, benchmark_profile=benchmark_profile),
    )

    for attempt in range(max_repairs + 1):
        print(f"[baseline] attempt {attempt + 1}/{max_repairs + 1}")
        try:
            validate_generated_repo(parsed)
        except OutputValidationError as exc:
            if attempt == max_repairs:
                raise RuntimeError(
                    "Generated repository failed semantic validation after repair attempts.\n"
                    f"{exc}"
                ) from exc

            print(
                f"[baseline] validation failed ({exc}); "
                f"requesting repair {attempt + 1}/{max_repairs}"
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
                    benchmark_profile=benchmark_profile,
                ),
            )
            continue

        reset_directory(output_dir)
        write_artifacts(output_dir, parsed.files)
        result = run_maven_tests(output_dir, verify_cmd)
        if result.passed:
            print("[baseline] verify passed")
            return parsed

        if attempt == max_repairs:
            print("[baseline] verify failed; no repair attempts remain")
            raise RuntimeError(
                "Generated repository failed verification after repair attempts.\n"
                f"Exit code: {result.exit_code}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )

        print(
            f"[baseline] verify failed "
            f"(exit={result.exit_code}, failures={result.failures}, errors={result.errors}). "
            f"requesting repair {attempt + 1}/{max_repairs}"
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
                benchmark_profile=benchmark_profile,
            ),
        )

    raise RuntimeError("Unreachable repository generation state.")
