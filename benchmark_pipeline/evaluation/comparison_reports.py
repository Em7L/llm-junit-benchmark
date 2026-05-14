from __future__ import annotations

"""Comparison-report helpers for multi-model benchmark runs."""

from pathlib import Path

from benchmark_pipeline.classifications import (
    DISABLING_CLASSIFICATIONS,
    REPAIR_CLASSIFICATIONS,
    classify_disabling,
    selected_definitions,
)
from benchmark_pipeline.evaluation.runner import EvaluationSuiteRun
from benchmark_pipeline.fs_utils import dump_json
from benchmark_pipeline.models import GeneratedTests


def write_comparison_reports(
    *,
    repo_model: str,
    tests_models: list[str],
    suite_names: dict[str, str],
    baseline_repo: Path,
    report_json: Path,
    report_md: Path,
    generated_tests: dict[str, GeneratedTests],
    test_generation_errors: dict[str, str],
    evaluations: list[EvaluationSuiteRun],
    initial_evaluations: dict[str, EvaluationSuiteRun | object],
) -> None:
    payload = comparison_payload(
        repo_model=repo_model,
        tests_models=tests_models,
        suite_names=suite_names,
        baseline_repo=baseline_repo,
        generated_tests=generated_tests,
        test_generation_errors=test_generation_errors,
        evaluations=evaluations,
        initial_evaluations=initial_evaluations,
    )
    comparison_json = report_json.parent / "comparison_report.json"
    comparison_md = report_md.parent / "comparison_report.md"
    print(f"[pipeline] Writing comparison JSON report to {comparison_json.resolve()}")
    dump_json(comparison_json, payload)
    comparison_md.parent.mkdir(parents=True, exist_ok=True)
    print(f"[pipeline] Writing comparison markdown report to {comparison_md.resolve()}")
    comparison_md.write_text(comparison_markdown(payload), encoding="utf-8")


def comparison_payload(
    *,
    repo_model: str,
    tests_models: list[str],
    suite_names: dict[str, str],
    baseline_repo: Path,
    generated_tests: dict[str, GeneratedTests],
    test_generation_errors: dict[str, str],
    evaluations: list[EvaluationSuiteRun],
    initial_evaluations: dict[str, object],
) -> dict[str, object]:
    evaluations_by_suite = {run.suite_name: run for run in evaluations}
    rows: list[dict[str, object]] = []

    for model in tests_models:
        suite_name = suite_names[model]
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
        initial_outcome = initial_evaluations.get(suite_name)
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
                "repair_outcome": generated.repair_outcome if generated is not None else None,
                "repair_attempts": generated.repair_attempts if generated is not None else None,
                "initial_evaluation_status": (
                    outcome.initial_baseline_result.status if outcome.initial_baseline_result is not None else outcome.baseline_result.status
                ),
                "disabling_outcome": classify_disabling(
                    baseline_result=outcome.baseline_result,
                    disabled_tests=outcome.disabled_tests,
                    initial_baseline_result=outcome.initial_baseline_result,
                ),
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
                "before_repair": evaluation_snapshot(initial_outcome),
                "after_repair": evaluation_snapshot(outcome),
            }
        )

    return {
        "repo_model": repo_model,
        "test_models": tests_models,
        "baseline_repo": baseline_repo.as_posix(),
        "mutant_set": mutant_set_summary(evaluations),
        "rows": rows,
    }


def evaluation_snapshot(outcome: object | None) -> dict[str, object] | None:
    from benchmark_pipeline.evaluation import EvaluationOutcome

    if not isinstance(outcome, EvaluationOutcome):
        return None

    coverage = outcome.baseline_coverage
    pitest = outcome.pitest_result
    initial_status = outcome.initial_baseline_result.status if outcome.initial_baseline_result is not None else outcome.baseline_result.status
    disabling = classify_disabling(
        baseline_result=outcome.baseline_result,
        disabled_tests=outcome.disabled_tests,
        initial_baseline_result=outcome.initial_baseline_result,
    )
    return {
        "initial_evaluation_status": initial_status,
        "disabling_outcome": disabling,
        "evaluation_status": outcome.baseline_result.status,
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

    other_mutants_by_suite = {
        suite: set().union(*(other for other_suite, other in suite_mutants.items() if other_suite != suite))
        for suite in suite_mutants
    }

    return {
        "comparable_suite_count": len(suite_mutants),
        "identical": identical,
        "common_mutants": len(common_mutants),
        "union_mutants": len(union_mutants),
        "per_suite_mutants": {suite: len(mutants) for suite, mutants in suite_mutants.items()},
        "only_in_suite": {
            suite: sorted(mutants - other_mutants_by_suite[suite]) for suite, mutants in suite_mutants.items()
        },
    }


def comparison_markdown(payload: dict[str, object]) -> str:
    rows = payload["rows"]
    assert isinstance(rows, list)
    has_repair_attempts = any(
        isinstance(row, dict) and isinstance(row.get("repair_attempts"), int) and row.get("repair_attempts", 0) > 0
        for row in rows
    )
    lines = [
        "# Model Comparison Report",
        "",
        f"- Repository model: `{payload['repo_model']}`",
        f"- Baseline repository: `{payload['baseline_repo']}`",
    ]
    lines.extend(
        render_comparison_table(
            title="Before Repair And Disabling",
            rows=rows,
            snapshot_key="before_repair",
            include_repair_columns=True,
        )
    )
    if has_repair_attempts:
        lines.extend(
            render_comparison_table(
                title="After Repair And Disabling",
                rows=rows,
                snapshot_key="after_repair",
                include_repair_columns=True,
            )
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
    repair_names = [
        row.get("repair_outcome")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("repair_outcome"), str)
    ]
    disabling_names = [
        row.get("disabling_outcome")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("disabling_outcome"), str)
    ]
    repair_definitions = selected_definitions(REPAIR_CLASSIFICATIONS, repair_names)
    disabling_definitions = selected_definitions(DISABLING_CLASSIFICATIONS, disabling_names)
    if repair_definitions or disabling_definitions:
        lines.extend(["", "## Classification Definitions"])
        for name, description in repair_definitions:
            lines.append(f"- `{name}`: {description}")
        for name, description in disabling_definitions:
            lines.append(f"- `{name}`: {description}")
    return "\n".join(lines)


def render_comparison_table(
    *,
    title: str,
    rows: list[object],
    snapshot_key: str,
    include_repair_columns: bool,
) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| Test model | Generation | Repair | Repair tries | Initial eval. | Disabling | Final eval. | Tests | Failures | Errors | Skipped | Disabled | Line cov. | Branch cov. | Mutations | Killed | Survived | No coverage | Mutation score |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        assert isinstance(row, dict)
        snapshot = row.get(snapshot_key)
        snapshot_dict = snapshot if isinstance(snapshot, dict) else {}
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(row.get("test_model")),
                    markdown_cell(row.get("generation_status")),
                    markdown_cell(row.get("repair_outcome")) if include_repair_columns else "N/A",
                    markdown_cell(row.get("repair_attempts")) if include_repair_columns else "N/A",
                    markdown_cell(snapshot_dict.get("initial_evaluation_status")),
                    markdown_cell(snapshot_dict.get("disabling_outcome")),
                    markdown_cell(snapshot_dict.get("evaluation_status")),
                    markdown_cell(snapshot_dict.get("tests")),
                    markdown_cell(snapshot_dict.get("failures")),
                    markdown_cell(snapshot_dict.get("errors")),
                    markdown_cell(snapshot_dict.get("skipped")),
                    markdown_cell(snapshot_dict.get("disabled_tests")),
                    percent_cell(snapshot_dict.get("line_coverage")),
                    percent_cell(snapshot_dict.get("branch_coverage")),
                    markdown_cell(snapshot_dict.get("total_mutations")),
                    markdown_cell(snapshot_dict.get("killed")),
                    markdown_cell(snapshot_dict.get("survived")),
                    markdown_cell(snapshot_dict.get("no_coverage")),
                    percent_cell(snapshot_dict.get("mutation_score")),
                ]
            )
            + " |"
        )
    return lines


def markdown_cell(value: object) -> str:
    return "N/A" if value is None else str(value)


def percent_cell(value: object) -> str:
    return "N/A" if not isinstance(value, int | float) else f"{value:.2%}"
