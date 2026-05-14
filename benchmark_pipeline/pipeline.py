from __future__ import annotations

"""End-to-end benchmark pipeline orchestration."""

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import Sequence
import concurrent.futures

from benchmark_pipeline.evaluation import EvaluationOutcome, evaluate_repositories
from benchmark_pipeline.evaluation.comparison_reports import write_comparison_reports
from benchmark_pipeline.evaluation.runner import EvaluationRunConfig, EvaluationSuiteRun, run_evaluation
from benchmark_pipeline.fs_utils import directories_match, dump_json, reset_directory
from benchmark_pipeline.generation.profiles import BenchmarkProfile
from benchmark_pipeline.generation.runner import (
    BaselineGenerationConfig,
    TestGenerationConfig,
    run_baseline_generation,
    run_test_generation,
)
from benchmark_pipeline.models import GeneratedRepo, GeneratedTests


@dataclass(frozen=True)
class PipelineConfig:
    repo_model: str
    tests_models: Sequence[str]
    benchmark_profile: BenchmarkProfile
    project_name: str
    baseline_repo: Path
    tests_dir: Path
    profile_manifest: Path
    baseline_manifest: Path
    tests_manifest: Path
    report_json: Path
    report_md: Path
    pitest_report_dir: Path
    maven_cmd: Sequence[str]
    max_repairs: int


@dataclass
class PipelineOutcome:
    generated_repo: GeneratedRepo
    generated_tests: dict[str, GeneratedTests]
    test_generation_errors: dict[str, str]
    evaluations: list[EvaluationSuiteRun]

    @property
    def evaluation(self) -> EvaluationOutcome:
        return self.evaluations[0].outcome


def run_pipeline(config: PipelineConfig) -> PipelineOutcome:
    if not config.tests_models:
        raise ValueError("At least one test-generation model must be provided.")

    print()
    print("=" * 72)
    print("[pipeline] Running full benchmark pipeline")
    print(f"[pipeline] Repository model: {config.repo_model}")
    print(f"[pipeline] Benchmark profile: {config.benchmark_profile.profile_id}")
    print(f"[pipeline] Test models: {', '.join(config.tests_models)}")
    print("=" * 72)

    print(f"[pipeline] Writing benchmark profile manifest to {config.profile_manifest.resolve()}")
    dump_json(config.profile_manifest, config.benchmark_profile.to_dict())

    print_step("baseline generation")
    generated_repo = run_baseline_generation(
        BaselineGenerationConfig(
            model=config.repo_model,
            project_name=config.project_name,
            output_dir=config.baseline_repo,
            manifest_path=config.baseline_manifest,
            verify_cmd=config.maven_cmd,
            max_repairs=config.max_repairs,
            benchmark_profile=config.benchmark_profile,
        )
    )
    print_step_done("baseline generation")

    print_step("test generation")
    generated_tests: dict[str, GeneratedTests] = {}
    test_generation_errors: dict[str, str] = {}
    suite_names = {model: safe_model_name(model) for model in config.tests_models}
    initial_tests_root = config.tests_dir / "_initial"
    reset_directory(config.tests_dir)
    def generate_for_model(model: str) -> tuple[str, GeneratedTests | None, str | None]:
        suite_name = suite_names[model]
        suite_dir = config.tests_dir / suite_name
        try:
            tests = run_test_generation(
                TestGenerationConfig(
                    repo_dir=config.baseline_repo,
                    output_dir=suite_dir,
                    model=model,
                    manifest_path=test_manifest_path(config.tests_manifest, suite_name, len(config.tests_models) > 1),
                    max_repairs=config.max_repairs,
                    initial_output_dir=initial_tests_root / suite_name,
                )
            )
            return (model, tests, None)
        except Exception as exc:
            if suite_dir.exists():
                shutil.rmtree(suite_dir, ignore_errors=True)
            initial_suite_dir = initial_tests_root / suite_name
            if initial_suite_dir.exists():
                shutil.rmtree(initial_suite_dir, ignore_errors=True)
            print(f"[pipeline] Test generation failed for `{model}`: {exc}")
            return (model, None, str(exc))

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(config.tests_models)) as executor:
        futures = {executor.submit(generate_for_model, model): model for model in config.tests_models}
        for future in concurrent.futures.as_completed(futures):
            model, tests, error = future.result()
            if tests is not None:
                generated_tests[model] = tests
            if error is not None:
                test_generation_errors[model] = error

    if not generated_tests:
        print("[pipeline] All test-generation models failed. Skipping PIT evaluation.")
        write_comparison_reports(
            repo_model=config.repo_model,
            benchmark_profile=config.benchmark_profile,
            tests_models=list(config.tests_models),
            suite_names=suite_names,
            baseline_repo=config.baseline_repo,
            report_json=config.report_json,
            report_md=config.report_md,
            generated_tests=generated_tests,
            test_generation_errors=test_generation_errors,
            evaluations=[],
            initial_evaluations={},
        )
        print_step_done("test generation")
        print()
        print("[pipeline] Full pipeline completed with no evaluable test suites")
        return PipelineOutcome(
            generated_repo=generated_repo,
            generated_tests=generated_tests,
            test_generation_errors=test_generation_errors,
            evaluations=[],
        )
    print_step_done("test generation")

    print_step("PIT evaluation")
    evaluations = run_evaluation(
        EvaluationRunConfig(
            baseline_repo=config.baseline_repo,
            tests_dir=config.tests_dir,
            pitest_report_dir=config.pitest_report_dir,
            maven_cmd=config.maven_cmd,
        )
    )
    evaluations_by_suite = {run.suite_name: run.outcome for run in evaluations}
    initial_evaluations: dict[str, EvaluationOutcome] = {}
    for model, generated in generated_tests.items():
        if generated.repair_attempts == 0:
            continue
        suite_name = suite_names[model]
        initial_suite_dir = initial_tests_root / suite_name
        if not initial_suite_dir.exists():
            continue
        final_suite_dir = config.tests_dir / suite_name
        if final_suite_dir.exists() and directories_match(initial_suite_dir, final_suite_dir):
            print(
                f"[pipeline] Reusing final evaluation for `{model}` because the initial and final suites are identical."
            )
            initial_evaluations[suite_name] = evaluations_by_suite[suite_name]
            continue
        initial_evaluations[suite_name] = evaluate_repositories(
            baseline_repo=config.baseline_repo,
            tests_dir=initial_suite_dir,
            maven_cmd=config.maven_cmd,
        )
    write_comparison_reports(
        repo_model=config.repo_model,
        benchmark_profile=config.benchmark_profile,
        tests_models=list(config.tests_models),
        suite_names=suite_names,
        baseline_repo=config.baseline_repo,
        report_json=config.report_json,
        report_md=config.report_md,
        generated_tests=generated_tests,
        test_generation_errors=test_generation_errors,
        evaluations=evaluations,
        initial_evaluations=initial_evaluations,
    )
    print_step_done("PIT evaluation")

    print()
    print("[pipeline] Full pipeline completed successfully")
    return PipelineOutcome(
        generated_repo=generated_repo,
        generated_tests=generated_tests,
        test_generation_errors=test_generation_errors,
        evaluations=evaluations,
    )


def safe_model_name(model: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", model.strip())
    return safe_name or "model"


def test_manifest_path(base_path: Path, suite_name: str, is_multi_model: bool) -> Path:
    if base_path.suffix and not is_multi_model:
        return base_path
    if base_path.suffix:
        return base_path.parent / f"{base_path.stem}_{suite_name}{base_path.suffix}"
    return base_path / f"{suite_name}_tests.json"


def print_step(label: str) -> None:
    print()
    print("=" * 72)
    print(f"[pipeline] Starting {label}")
    print("=" * 72)


def print_step_done(label: str) -> None:
    print(f"[pipeline] Completed {label}")
