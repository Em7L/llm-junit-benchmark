from __future__ import annotations

"""End-to-end benchmark pipeline orchestration."""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from benchmark_pipeline.evaluation import EvaluationOutcome, evaluate_repositories, write_evaluation_json
from benchmark_pipeline.fs_utils import dump_json
from benchmark_pipeline.models import GeneratedRepo, GeneratedTests
from benchmark_pipeline.repo_generation import generate_verified_repo
from benchmark_pipeline.reports import markdown_report
from benchmark_pipeline.tests_generation import generate_tests


@dataclass(frozen=True)
class PipelineConfig:
    repo_model: str
    tests_model: str
    project_name: str
    baseline_repo: Path
    tests_dir: Path
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
    generated_tests: GeneratedTests
    evaluation: EvaluationOutcome


def run_pipeline(config: PipelineConfig) -> PipelineOutcome:
    print()
    print("=" * 72)
    print("[pipeline] Running full benchmark pipeline")
    print(f"[pipeline] Repository model: {config.repo_model}")
    print(f"[pipeline] Test model: {config.tests_model}")
    print("=" * 72)

    print_step("baseline generation")
    generated_repo = generate_verified_repo(
        model=config.repo_model,
        project_name=config.project_name,
        output_dir=config.baseline_repo,
        max_repairs=config.max_repairs,
        verify_cmd=list(config.maven_cmd),
    )
    print(f"[baseline] Writing manifest to {config.baseline_manifest.resolve()}")
    dump_json(config.baseline_manifest, generated_repo.model_dump())
    print_step_done("baseline generation")

    print_step("test generation")
    generated_tests = generate_tests(
        repo_dir=config.baseline_repo,
        output_dir=config.tests_dir,
        model=config.tests_model,
    )
    print(f"[tests] Writing manifest to {config.tests_manifest.resolve()}")
    dump_json(config.tests_manifest, generated_tests.model_dump())
    print_step_done("test generation")

    print_step("PIT evaluation")
    evaluation = evaluate_repositories(
        baseline_repo=config.baseline_repo,
        tests_dir=config.tests_dir,
        maven_cmd=config.maven_cmd,
        pitest_report_dir=config.pitest_report_dir,
    )
    write_reports(config, evaluation)
    print_step_done("PIT evaluation")

    print()
    print("[pipeline] Full pipeline completed successfully")
    return PipelineOutcome(
        generated_repo=generated_repo,
        generated_tests=generated_tests,
        evaluation=evaluation,
    )


def write_reports(config: PipelineConfig, outcome: EvaluationOutcome) -> None:
    print(f"[evaluation] Writing JSON report to {config.report_json.resolve()}")
    write_evaluation_json(config.report_json, outcome)
    config.report_md.parent.mkdir(parents=True, exist_ok=True)
    print(f"[evaluation] Writing markdown report to {config.report_md.resolve()}")
    config.report_md.write_text(
        markdown_report(
            outcome.baseline_result,
            outcome.baseline_coverage,
            outcome.pitest_result,
            outcome.disabled_tests,
            outcome.initial_baseline_result,
        ),
        encoding="utf-8",
    )


def print_step(label: str) -> None:
    print()
    print("=" * 72)
    print(f"[pipeline] Starting {label}")
    print("=" * 72)


def print_step_done(label: str) -> None:
    print(f"[pipeline] Completed {label}")
