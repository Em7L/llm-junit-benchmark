from __future__ import annotations

"""End-to-end benchmark pipeline orchestration."""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from benchmark_pipeline.evaluation import EvaluationOutcome
from benchmark_pipeline.evaluation.runner import EvaluationRunConfig, run_evaluation
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
    generated_repo = run_baseline_generation(
        BaselineGenerationConfig(
            model=config.repo_model,
            project_name=config.project_name,
            output_dir=config.baseline_repo,
            manifest_path=config.baseline_manifest,
            verify_cmd=config.maven_cmd,
            max_repairs=config.max_repairs,
        )
    )
    print_step_done("baseline generation")

    print_step("test generation")
    generated_tests = run_test_generation(
        TestGenerationConfig(
            repo_dir=config.baseline_repo,
            output_dir=config.tests_dir,
            model=config.tests_model,
            manifest_path=config.tests_manifest,
            max_repairs=config.max_repairs,
        )
    )
    print_step_done("test generation")

    print_step("PIT evaluation")
    evaluation_runs = run_evaluation(
        EvaluationRunConfig(
            baseline_repo=config.baseline_repo,
            tests_dir=config.tests_dir,
            report_json=config.report_json,
            report_md=config.report_md,
            pitest_report_dir=config.pitest_report_dir,
            maven_cmd=config.maven_cmd,
        )
    )
    evaluation = evaluation_runs[0].outcome
    print_step_done("PIT evaluation")

    print()
    print("[pipeline] Full pipeline completed successfully")
    return PipelineOutcome(
        generated_repo=generated_repo,
        generated_tests=generated_tests,
        evaluation=evaluation,
    )


def print_step(label: str) -> None:
    print()
    print("=" * 72)
    print(f"[pipeline] Starting {label}")
    print("=" * 72)


def print_step_done(label: str) -> None:
    print(f"[pipeline] Completed {label}")
