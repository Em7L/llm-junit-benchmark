from __future__ import annotations

"""End-to-end benchmark pipeline orchestration."""

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import Sequence

from benchmark_pipeline.evaluation import EvaluationOutcome
from benchmark_pipeline.evaluation.runner import EvaluationRunConfig, EvaluationSuiteRun, run_evaluation
from benchmark_pipeline.generation.runner import (
    BaselineGenerationConfig,
    TestGenerationConfig,
    run_baseline_generation,
    run_test_generation,
)
from benchmark_pipeline.fs_utils import dump_json, reset_directory
from benchmark_pipeline.models import GeneratedRepo, GeneratedTests


@dataclass(frozen=True)
class PipelineConfig:
    repo_model: str
    tests_models: Sequence[str]
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
    print(f"[pipeline] Test models: {', '.join(config.tests_models)}")
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
    generated_tests: dict[str, GeneratedTests] = {}
    test_generation_errors: dict[str, str] = {}
    reset_directory(config.tests_dir)
    for model in config.tests_models:
        suite_name = safe_model_name(model)
        suite_dir = config.tests_dir / suite_name
        try:
            generated_tests[model] = run_test_generation(
                TestGenerationConfig(
                    repo_dir=config.baseline_repo,
                    output_dir=suite_dir,
                    model=model,
                    manifest_path=test_manifest_path(config.tests_manifest, suite_name, len(config.tests_models) > 1),
                    max_repairs=config.max_repairs,
                )
            )
        except Exception as exc:
            test_generation_errors[model] = str(exc)
            if suite_dir.exists():
                shutil.rmtree(suite_dir, ignore_errors=True)
            print(f"[pipeline] Test generation failed for `{model}`: {exc}")

    if not generated_tests:
        raise RuntimeError(
            "All test-generation models failed. "
            "No test suites are available for evaluation.\n"
            + "\n".join(f"- {model}: {error}" for model, error in test_generation_errors.items())
        )
    print_step_done("test generation")

    print_step("PIT evaluation")
    evaluations = run_evaluation(
        EvaluationRunConfig(
            baseline_repo=config.baseline_repo,
            tests_dir=config.tests_dir,
            report_json=config.report_json,
            report_md=config.report_md,
            pitest_report_dir=config.pitest_report_dir,
            maven_cmd=config.maven_cmd,
        )
    )
    write_comparison_reports(config, generated_tests, test_generation_errors, evaluations)
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


def write_comparison_reports(
    config: PipelineConfig,
    generated_tests: dict[str, GeneratedTests],
    test_generation_errors: dict[str, str],
    evaluations: list[EvaluationSuiteRun],
) -> None:
    payload = comparison_payload(config, generated_tests, test_generation_errors, evaluations)
    report_json = config.report_json.parent / "comparison_report.json"
    report_md = config.report_md.parent / "comparison_report.md"
    print(f"[pipeline] Writing comparison JSON report to {report_json.resolve()}")
    dump_json(report_json, payload)
    report_md.parent.mkdir(parents=True, exist_ok=True)
    print(f"[pipeline] Writing comparison markdown report to {report_md.resolve()}")
    report_md.write_text(comparison_markdown(payload), encoding="utf-8")


def comparison_payload(
    config: PipelineConfig,
    generated_tests: dict[str, GeneratedTests],
    test_generation_errors: dict[str, str],
    evaluations: list[EvaluationSuiteRun],
) -> dict[str, object]:
    evaluations_by_suite = {run.suite_name: run for run in evaluations}
    rows: list[dict[str, object]] = []

    for model in config.tests_models:
        suite_name = safe_model_name(model)
        error = test_generation_errors.get(model)
        if error is not None:
            rows.append(
                {
                    "test_model": model,
                    "suite_name": suite_name,
                    "generation_status": "failed",
                    "error": error,
                }
            )
            continue

        generated = generated_tests.get(model)
        run = evaluations_by_suite.get(suite_name)
        if run is None:
            rows.append(
                {
                    "test_model": model,
                    "suite_name": suite_name,
                    "generation_status": "passed" if generated is not None else "missing",
                    "evaluation_status": "missing",
                    "generated_test_files": len(generated.files) if generated is not None else None,
                }
            )
            continue

        outcome = run.outcome
        coverage = outcome.baseline_coverage
        pitest = outcome.pitest_result
        rows.append(
            {
                "test_model": model,
                "suite_name": suite_name,
                "generation_status": "passed",
                "evaluation_status": outcome.baseline_result.status,
                "generated_test_files": len(generated.files) if generated is not None else None,
                "tests": outcome.baseline_result.tests,
                "failures": outcome.baseline_result.failures,
                "errors": outcome.baseline_result.errors,
                "skipped": outcome.baseline_result.skipped,
                "disabled_tests": len(outcome.disabled_tests),
                "line_coverage": coverage.line_rate if coverage is not None else None,
                "branch_coverage": coverage.branch_rate if coverage is not None else None,
                "instruction_coverage": coverage.instruction_rate if coverage is not None else None,
                "total_mutations": pitest.total_mutations if pitest is not None else None,
                "killed": pitest.status_counts.get("KILLED", 0) if pitest is not None else None,
                "survived": pitest.status_counts.get("SURVIVED", 0) if pitest is not None else None,
                "no_coverage": pitest.status_counts.get("NO_COVERAGE", 0) if pitest is not None else None,
                "mutation_score": pitest.mutation_score if pitest is not None else None,
                "report_json": run.report_json.as_posix(),
                "report_md": run.report_md.as_posix(),
            }
        )

    return {
        "repo_model": config.repo_model,
        "test_models": list(config.tests_models),
        "baseline_repo": config.baseline_repo.as_posix(),
        "mutant_set": mutant_set_summary(evaluations),
        "rows": rows,
    }


def mutant_set_summary(evaluations: list[EvaluationSuiteRun]) -> dict[str, object]:
    suite_mutants: dict[str, set[str]] = {}
    for run in evaluations:
        pitest = run.outcome.pitest_result
        if pitest is None:
            continue
        suite_mutants[run.suite_name] = {mutation.mutant_id for mutation in pitest.mutations}

    if not suite_mutants:
        return {
            "comparable_suite_count": 0,
            "identical": None,
            "common_mutants": 0,
            "union_mutants": 0,
            "per_suite_mutants": {},
            "only_in_suite": {},
        }

    mutant_sets = list(suite_mutants.values())
    common_mutants = set.intersection(*mutant_sets)
    union_mutants = set.union(*mutant_sets)
    first_set = mutant_sets[0]
    identical = all(mutants == first_set for mutants in mutant_sets)

    return {
        "comparable_suite_count": len(suite_mutants),
        "identical": identical,
        "common_mutants": len(common_mutants),
        "union_mutants": len(union_mutants),
        "per_suite_mutants": {suite: len(mutants) for suite, mutants in suite_mutants.items()},
        "only_in_suite": {
            suite: sorted(mutants - set.union(*(other for other_suite, other in suite_mutants.items() if other_suite != suite)))
            if len(suite_mutants) > 1
            else []
            for suite, mutants in suite_mutants.items()
        },
    }


def comparison_markdown(payload: dict[str, object]) -> str:
    rows = payload["rows"]
    assert isinstance(rows, list)
    lines = [
        "# Model Comparison Report",
        "",
        f"- Repository model: `{payload['repo_model']}`",
        f"- Baseline repository: `{payload['baseline_repo']}`",
        "",
        "| Test model | Generation | Evaluation | Tests | Skipped | Disabled | Line cov. | Branch cov. | Mutations | Killed | Survived | No coverage | Mutation score |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        assert isinstance(row, dict)
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(row.get("test_model")),
                    markdown_cell(row.get("generation_status")),
                    markdown_cell(row.get("evaluation_status")),
                    markdown_cell(row.get("tests")),
                    markdown_cell(row.get("skipped")),
                    markdown_cell(row.get("disabled_tests")),
                    percent_cell(row.get("line_coverage")),
                    percent_cell(row.get("branch_coverage")),
                    markdown_cell(row.get("total_mutations")),
                    markdown_cell(row.get("killed")),
                    markdown_cell(row.get("survived")),
                    markdown_cell(row.get("no_coverage")),
                    percent_cell(row.get("mutation_score")),
                ]
            )
            + " |"
        )

    failed_rows = [row for row in rows if isinstance(row, dict) and row.get("error")]
    if failed_rows:
        lines.extend(["", "## Generation Failures"])
        for row in failed_rows:
            lines.append(f"- `{row['test_model']}`: {row['error']}")
    mutant_set = payload.get("mutant_set")
    if isinstance(mutant_set, dict):
        lines.extend(
            [
                "",
                "## Mutant Set Consistency",
                f"- Comparable PIT suites: `{mutant_set.get('comparable_suite_count')}`",
                f"- Identical mutant IDs across suites: `{mutant_set.get('identical')}`",
                f"- Common mutant IDs: `{mutant_set.get('common_mutants')}`",
                f"- Union mutant IDs: `{mutant_set.get('union_mutants')}`",
            ]
        )
        per_suite = mutant_set.get("per_suite_mutants")
        if isinstance(per_suite, dict):
            for suite_name, mutant_count in sorted(per_suite.items()):
                lines.append(f"- `{suite_name}` mutant IDs: `{mutant_count}`")
    return "\n".join(lines)


def markdown_cell(value: object) -> str:
    return "N/A" if value is None else str(value)


def percent_cell(value: object) -> str:
    return "N/A" if not isinstance(value, int | float) else f"{value:.2%}"


def print_step(label: str) -> None:
    print()
    print("=" * 72)
    print(f"[pipeline] Starting {label}")
    print("=" * 72)


def print_step_done(label: str) -> None:
    print(f"[pipeline] Completed {label}")
