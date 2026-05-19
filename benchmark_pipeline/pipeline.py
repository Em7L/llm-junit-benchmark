from __future__ import annotations

"""End-to-end benchmark pipeline orchestration."""

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import Sequence
import concurrent.futures

from benchmark_pipeline.cli_output import heading, kv, relpath
from benchmark_pipeline.evaluation import EvaluationOutcome
from benchmark_pipeline.evaluation.comparison_reports import write_comparison_reports
from benchmark_pipeline.evaluation.runner import EvaluationRunConfig, EvaluationSuiteRun, run_evaluation
from benchmark_pipeline.fs_utils import (
    directories_match,
    dump_json,
    remove_named_directories,
    remove_staging_root,
    reset_directory,
)
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
    benchmark_profile: BenchmarkProfile | None
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
    def evaluation(self) -> EvaluationOutcome | None:
        return self.evaluations[0].outcome if self.evaluations else None


def run_pipeline(config: PipelineConfig) -> PipelineOutcome:
    if not config.tests_models:
        raise ValueError("At least one test-generation model must be provided.")

    heading("[pipeline]", "Run started")
    kv("[pipeline]", "run", relpath(config.baseline_repo.parent))
    kv("[pipeline]", "repo model", config.repo_model)
    kv(
        "[pipeline]",
        "profile",
        config.benchmark_profile.profile_id if config.benchmark_profile is not None else "auto-selected by model",
    )
    kv("[pipeline]", "test models", ", ".join(config.tests_models))
    dump_json(
        config.profile_manifest,
        (
            config.benchmark_profile.to_dict()
            if config.benchmark_profile is not None
            else {"profile_id": None, "complexity": None, "selection_mode": "model_selected"}
        ),
    )

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
    final_selected_tests_root = config.tests_dir / "_final_selected"
    initial_snapshot_tests_root = config.tests_dir / "_initial_snapshot"
    reset_directory(config.tests_dir)
    final_selected_tests_root.mkdir(parents=True, exist_ok=True)
    initial_snapshot_tests_root.mkdir(parents=True, exist_ok=True)
    def generate_for_model(model: str) -> tuple[str, GeneratedTests | None, str | None]:
        suite_name = suite_names[model]
        suite_dir = final_selected_tests_root / suite_name
        try:
            tests = run_test_generation(
                TestGenerationConfig(
                    repo_dir=config.baseline_repo,
                    output_dir=suite_dir,
                    model=model,
                    manifest_path=test_manifest_path(config.tests_manifest, suite_name, len(config.tests_models) > 1),
                    max_repairs=config.max_repairs,
                    initial_output_dir=initial_snapshot_tests_root / suite_name,
                )
            )
            return (model, tests, None)
        except Exception as exc:
            if suite_dir.exists():
                shutil.rmtree(suite_dir, ignore_errors=True)
            initial_suite_dir = initial_snapshot_tests_root / suite_name
            if initial_suite_dir.exists():
                shutil.rmtree(initial_suite_dir, ignore_errors=True)
            print(f"[pipeline] test generation failed for `{model}`: {exc}")
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
        print("[pipeline] all test-generation models failed; skipping PIT evaluation")
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
        heading("[pipeline]", "Run finished")
        print("[pipeline] no evaluable test suites")
        cleanup_published_artifacts(config)
        remove_staging_root(config.baseline_repo)
        return PipelineOutcome(
            generated_repo=generated_repo,
            generated_tests=generated_tests,
            test_generation_errors=test_generation_errors,
            evaluations=[],
        )
    print_step_done("test generation")

    print_step("PIT evaluation")
    evaluations = run_evaluation_for_suites(
        baseline_repo=config.baseline_repo,
        tests_dir=final_selected_tests_root,
        pitest_report_dir=config.pitest_report_dir / "_final_selected",
        maven_cmd=config.maven_cmd,
    )
    evaluations_by_suite = evaluation_map_by_suite_name(evaluations)
    initial_evaluations: dict[str, object] = {}
    for model, generated in generated_tests.items():
        if generated.repair_attempts == 0:
            continue
        suite_name = suite_names[model]
        initial_suite_dir = initial_snapshot_tests_root / suite_name
        if not initial_suite_dir.exists():
            continue
        final_suite_dir = final_selected_tests_root / suite_name
        if final_suite_dir.exists() and directories_match(initial_suite_dir, final_suite_dir):
            print(
                f"[pipeline] reusing final evaluation for `{model}`; initial and final generated test suites are identical"
            )
            initial_outcome = evaluations_by_suite.get(suite_name)
            if initial_outcome is not None:
                initial_evaluations[suite_name] = initial_outcome
            continue
        initial_evaluation = run_evaluation_for_suites(
            baseline_repo=config.baseline_repo,
            tests_dir=initial_suite_dir,
            pitest_report_dir=config.pitest_report_dir / "_initial_snapshot" / suite_name,
            maven_cmd=config.maven_cmd,
        )
        if initial_evaluation:
            initial_evaluations[suite_name] = initial_evaluation[0]
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

    heading("[pipeline]", "Run finished")
    kv("[pipeline]", "reports", relpath(config.report_md.parent))
    cleanup_published_artifacts(config)
    remove_staging_root(config.baseline_repo)
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
    heading("[pipeline]", f"{label.capitalize()}")


def print_step_done(label: str) -> None:
    print(f"[pipeline] {label} complete")


def cleanup_published_artifacts(config: PipelineConfig) -> None:
    remove_named_directories(config.baseline_repo, "target")
    remove_named_directories(config.tests_dir, "target")


def run_evaluation_for_suites(
    *,
    baseline_repo: Path,
    tests_dir: Path,
    pitest_report_dir: Path,
    maven_cmd: Sequence[str],
) -> list[EvaluationSuiteRun]:
    if not tests_dir.exists():
        return []
    return run_evaluation(
        EvaluationRunConfig(
            baseline_repo=baseline_repo,
            tests_dir=tests_dir,
            pitest_report_dir=pitest_report_dir,
            maven_cmd=maven_cmd,
        )
    )


def evaluation_map_by_suite_name(runs: list[EvaluationSuiteRun]) -> dict[str, EvaluationOutcome]:
    return {run.suite_name: run.outcome for run in runs}
