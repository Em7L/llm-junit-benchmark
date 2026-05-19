from __future__ import annotations

"""JUnit test-suite generation orchestration with repair loop."""

from pathlib import Path
import shutil

from benchmark_pipeline.classifications import classify_repair
from benchmark_pipeline.fs_utils import (
    reset_directory,
    stage_repo_with_artifacts,
    stage_repo_with_tests,
    write_artifacts,
)
from benchmark_pipeline.generation.prompts import build_test_prompt, build_test_repair_prompt
from benchmark_pipeline.generation.validation import OutputValidationError, validate_generated_tests
from benchmark_pipeline.models import GeneratedTests, MavenResult
from benchmark_pipeline.tools.llm import parse_structured_response
from benchmark_pipeline.tools.maven import run_maven_tests


GOOD_VERIFICATION_STATUSES = {"passed", "test_failures", "test_execution_failure"}


def count_test_files(generated_tests: GeneratedTests) -> int:
    return len({file.path for file in generated_tests.files})


def validate_repair_did_not_drop_suite(previous: GeneratedTests, repaired: GeneratedTests) -> None:
    previous_count = count_test_files(previous)
    repaired_count = count_test_files(repaired)
    if previous_count > 1 and repaired_count < previous_count:
        raise OutputValidationError(
            "Repair response appears to be incomplete: "
            f"previous suite had {previous_count} test files, repaired suite has {repaired_count}. "
            "Return the complete repaired test suite, including unchanged test files."
        )


def merge_repaired_tests(previous: GeneratedTests, updates: GeneratedTests) -> GeneratedTests:
    merged_files = {artifact.path: artifact for artifact in previous.files}
    for artifact in updates.files:
        merged_files[artifact.path] = artifact
    return GeneratedTests(
        summary=updates.summary or previous.summary,
        files=list(merged_files.values()),
        assumptions=updates.assumptions or previous.assumptions,
        repair_attempts=previous.repair_attempts,
        repair_outcome=previous.repair_outcome,
        repair_reasons=list(previous.repair_reasons),
    )


def compile_check_command(maven_cmd: list[str]) -> list[str] | None:
    if not maven_cmd:
        return None
    if maven_cmd[-1] != "test":
        return None
    return [*maven_cmd[:-1], "test-compile"]


def is_good_verification_result(result: MavenResult | None) -> bool:
    return result is not None and result.status in GOOD_VERIFICATION_STATUSES


def generate_tests(
    *,
    repo_dir: Path,
    output_dir: Path,
    model: str,
    max_repairs: int = 2,
    maven_cmd: list[str] | None = None,
    initial_output_dir: Path | None = None,
) -> GeneratedTests:
    if not repo_dir.exists():
        raise FileNotFoundError(f"Repository not found: {repo_dir}")
    if maven_cmd is None:
        maven_cmd = ["mvn", "test"]
    log_prefix = f"[tests: {model}]"

    print()
    print("-" * 72)
    print(f"{log_prefix} Test suite generation")
    print("-" * 72)
    print(f"{log_prefix} Reading baseline repository from {repo_dir.resolve()}")
    print(f"{log_prefix} Requesting initial generated test suite")

    parsed = parse_structured_response(
        model=model,
        schema=GeneratedTests,
        instructions=(
            "Generate a JUnit 5 test suite for the provided Java repository. "
            "Return only structured data that matches the schema."
        ),
        user_input=build_test_prompt(repo_dir),
    )
    repair_attempts = 0
    repair_reasons: list[str] = []
    first_verification_result: MavenResult | None = None
    last_good_suite: GeneratedTests | None = None
    last_good_result: MavenResult | None = None
    initial_snapshot_written = False
    result: MavenResult | None = None

    for attempt in range(max_repairs + 1):
        print()
        print(f"{log_prefix} Candidate attempt {attempt + 1}/{max_repairs + 1}")
        try:
            validate_generated_tests(parsed)
        except OutputValidationError as exc:
            if attempt == max_repairs:
                raise RuntimeError(
                    "Generated test suite failed semantic validation after repair attempts.\n"
                    f"{exc}"
                ) from exc

            print(
                f"{log_prefix} Validation failed ({exc}). "
                f"Requesting repair attempt {attempt + 1}/{max_repairs}"
            )
            previous = parsed
            repair_attempts += 1
            repair_reasons.append("semantic_validation")
            semantic_repair_root = stage_repo_with_artifacts(repo_dir, parsed.files)
            try:
                semantic_repair_context = build_test_repair_prompt(
                    repo_root=semantic_repair_root,
                    build_output=str(exc),
                    return_full_suite=True,
                )
            finally:
                if semantic_repair_root.exists():
                    shutil.rmtree(semantic_repair_root, ignore_errors=True)
            parsed = parse_structured_response(
                model=model,
                schema=GeneratedTests,
                instructions=(
                    "Repair the JUnit 5 test suite so it matches the expected Maven test structure. "
                    "Return only structured data that matches the schema."
                ),
                user_input=semantic_repair_context,
            )
            try:
                validate_repair_did_not_drop_suite(previous, parsed)
            except OutputValidationError as repair_exc:
                if attempt == max_repairs - 1:
                    raise RuntimeError(
                        "Generated test suite failed semantic validation after repair attempts.\n"
                        f"{repair_exc}"
                    ) from repair_exc
                print(f"{log_prefix} Repair response was incomplete ({repair_exc}). Requesting another repair.")
                parsed = previous
            continue

        if attempt == 0 and initial_output_dir is not None and not initial_snapshot_written:
            print(f"{log_prefix} Writing initial generated suite snapshot to {initial_output_dir.resolve()}")
            reset_directory(initial_output_dir)
            write_artifacts(initial_output_dir, parsed.files)
            initial_snapshot_written = True

        print(f"{log_prefix} Writing generated tests to {output_dir.resolve()}")
        reset_directory(output_dir)
        write_artifacts(output_dir, parsed.files)

        staged_dir = stage_repo_with_tests(repo_dir, output_dir)
        try:
            compile_cmd = compile_check_command(maven_cmd)
            if compile_cmd is not None:
                print(f"{log_prefix} Checking test compilation with: {' '.join(compile_cmd)}")
                compile_result = run_maven_tests(staged_dir, compile_cmd)
                if compile_result.status in {"test_compile_failure", "main_compile_failure"}:
                    result = compile_result
                else:
                    print(f"{log_prefix} Verifying test suite with: {' '.join(maven_cmd)}")
                    result = run_maven_tests(staged_dir, maven_cmd)
            else:
                print(f"{log_prefix} Verifying test suite with: {' '.join(maven_cmd)}")
                result = run_maven_tests(staged_dir, maven_cmd)
            if first_verification_result is None:
                first_verification_result = result
            repair_context = build_test_repair_prompt(
                repo_root=staged_dir,
                build_output=f"{result.stdout}\n{result.stderr}".strip(),
                return_full_suite=False,
            )
        finally:
            if staged_dir.exists():
                shutil.rmtree(staged_dir, ignore_errors=True)

        if result.passed:
            print(f"{log_prefix} Verification passed. Test suite is valid.")
            parsed.repair_attempts = repair_attempts
            parsed.repair_reasons = repair_reasons
            parsed.repair_outcome = classify_repair(
                repair_attempts=repair_attempts,
                first_verification_result=first_verification_result,
                final_verification_result=result,
            )
            return parsed

        if is_good_verification_result(result):
            last_good_suite = parsed
            last_good_result = result

        if attempt == max_repairs:
            if last_good_suite is not None and last_good_result is not None and last_good_suite is not parsed:
                print(
                    f"{log_prefix} Verification failed and no repair attempts remain. "
                    "Keeping the last still-runnable generated suite for evaluation."
                )
                parsed = last_good_suite
                result = last_good_result
                reset_directory(output_dir)
                write_artifacts(output_dir, parsed.files)
                break
            print(f"{log_prefix} Verification failed and no repair attempts remain. Keeping the final generated suite for evaluation.")
            break

        print(
            f"{log_prefix} Verification failed "
            f"(exit={result.exit_code}, failures={result.failures}, errors={result.errors}). "
            f"Requesting repair attempt {attempt + 1}/{max_repairs}"
        )
        previous = parsed
        repair_attempts += 1
        repair_reasons.append("verification_failure")
        repaired_updates = parse_structured_response(
            model=model,
            schema=GeneratedTests,
            instructions=(
                "Repair the JUnit 5 test suite so it compiles and passes verification. "
                "Return only structured data that matches the schema."
            ),
            user_input=repair_context,
        )
        parsed = merge_repaired_tests(previous, repaired_updates)

    parsed.repair_attempts = repair_attempts
    parsed.repair_reasons = repair_reasons
    parsed.repair_outcome = classify_repair(
        repair_attempts=repair_attempts,
        first_verification_result=first_verification_result,
        final_verification_result=result,
    )
    return parsed
