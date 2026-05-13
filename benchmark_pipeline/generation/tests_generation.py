from __future__ import annotations

"""JUnit test-suite generation orchestration with repair loop."""

from pathlib import Path
import shutil

from benchmark_pipeline.fs_utils import reset_directory, write_artifacts, stage_repo_with_tests
from benchmark_pipeline.tools.llm import parse_structured_response
from benchmark_pipeline.tools.maven import run_maven_tests
from benchmark_pipeline.models import GeneratedTests
from benchmark_pipeline.generation.prompts import build_test_prompt, build_test_repair_prompt
from benchmark_pipeline.generation.validation import OutputValidationError, validate_generated_tests


def generate_tests(*, repo_dir: Path, output_dir: Path, model: str, max_repairs: int = 2, maven_cmd: list[str] | None = None) -> GeneratedTests:
    if not repo_dir.exists():
        raise FileNotFoundError(f"Repository not found: {repo_dir}")
    if maven_cmd is None:
        maven_cmd = ["mvn", "test"]

    print()
    print("-" * 72)
    print(f"[tests] Test suite generation ({model})")
    print("-" * 72)
    print(f"[tests] Reading baseline repository from {repo_dir.resolve()}")
    print(f"[tests] Requesting initial generated test suite with model `{model}`")
    
    parsed = parse_structured_response(
        model=model,
        schema=GeneratedTests,
        instructions=(
            "Generate a JUnit 5 test suite for the provided Java repository. "
            "Return only structured data that matches the schema."
        ),
        user_input=build_test_prompt(repo_dir),
    )

    for attempt in range(max_repairs + 1):
        print()
        print(f"[tests] Candidate attempt {attempt + 1}/{max_repairs + 1}")
        try:
            validate_generated_tests(parsed)
        except OutputValidationError as exc:
            if attempt == max_repairs:
                raise RuntimeError(
                    "Generated test suite failed semantic validation after repair attempts.\n"
                    f"{exc}"
                ) from exc

            print(
                f"[tests] Validation failed ({exc}). "
                f"Requesting repair attempt {attempt + 1}/{max_repairs}"
            )
            parsed = parse_structured_response(
                model=model,
                schema=GeneratedTests,
                instructions=(
                    "Repair the JUnit 5 test suite so it matches the expected Maven test structure. "
                    "Return only structured data that matches the schema."
                ),
                user_input=build_test_repair_prompt(
                    repo_root=repo_dir,
                    build_output=str(exc),
                ),
            )
            continue

        print(f"[tests] Writing generated tests to {output_dir.resolve()}")
        reset_directory(output_dir)
        write_artifacts(output_dir, parsed.files)

        # Stage and verify
        staged_dir = stage_repo_with_tests(repo_dir, output_dir)
        try:
            print(f"[tests] Verifying test suite with: {' '.join(maven_cmd)}")
            result = run_maven_tests(staged_dir, maven_cmd)
        finally:
            if staged_dir.exists():
                shutil.rmtree(staged_dir, ignore_errors=True)

        if result.passed:
            print("[tests] Verification passed. Test suite is valid.")
            return parsed

        if attempt == max_repairs:
            print("[tests] Verification failed and no repair attempts remain. Keeping the final generated suite for evaluation.")
            break

        print(
            f"[tests] Verification failed "
            f"(exit={result.exit_code}, failures={result.failures}, errors={result.errors}). "
            f"Requesting repair attempt {attempt + 1}/{max_repairs}"
        )
        parsed = parse_structured_response(
            model=model,
            schema=GeneratedTests,
            instructions=(
                "Repair the JUnit 5 test suite so it compiles and passes verification. "
                "Return only structured data that matches the schema."
            ),
            user_input=build_test_repair_prompt(
                repo_root=repo_dir,
                build_output=f"{result.stdout}\n{result.stderr}".strip(),
            ),
        )

    return parsed

