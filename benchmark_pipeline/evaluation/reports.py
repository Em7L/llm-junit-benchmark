from __future__ import annotations

"""Report-formatting helpers for serializing and rendering evaluation results."""

from dataclasses import asdict

from benchmark_pipeline.classifications import (
    DISABLING_CLASSIFICATIONS,
    REPAIR_CLASSIFICATIONS,
    classify_disabling,
    selected_definitions,
)
from benchmark_pipeline.models import GeneratedTests, JacocoCoverage, MavenResult, PitestResult


def _append_maven_result(lines: list[str], result: MavenResult) -> None:
    lines.extend(
        [
            f"- Passed: `{result.passed}`",
            f"- Run status: `{result.status}`",
            f"- Exit code: `{result.exit_code}`",
            f"- Tests: `{result.tests}`",
            f"- Failures: `{result.failures}`",
            f"- Errors: `{result.errors}`",
            f"- Skipped: `{result.skipped}`",
        ]
    )
    if result.status_reason:
        lines.append(f"- Status reason: {result.status_reason}")
    if result.failing_tests:
        lines.append(f"- Failing tests: `{len(result.failing_tests)}`")


def markdown_report(
    baseline_result: MavenResult,
    baseline_coverage: JacocoCoverage | None,
    pitest_result: PitestResult | None,
    disabled_tests: list[str] | None = None,
    initial_baseline_result: MavenResult | None = None,
    generated_tests: GeneratedTests | None = None,
) -> str:
    disable_status = classify_disabling(
        baseline_result=baseline_result,
        disabled_tests=disabled_tests,
        initial_baseline_result=initial_baseline_result,
    )
    lines = [
        "# Mutation Evaluation Report",
        "",
    ]
    if generated_tests is not None:
        lines.extend(
            [
                "## Test Generation Repair",
                f"- Repair outcome: `{generated_tests.repair_outcome}`",
                f"- Repair attempts: `{generated_tests.repair_attempts}`",
                f"- Repair reasons: `{', '.join(generated_tests.repair_reasons) if generated_tests.repair_reasons else 'none'}`",
                "",
            ]
        )
    lines.extend(
        [
        "## Initial Baseline Validation",
        ]
    )
    _append_maven_result(lines, initial_baseline_result or baseline_result)
    if initial_baseline_result is not None:
        lines.extend(
            [
                "",
                "## Baseline-Failing Test Disabling",
                "- Disabling applied: `True`",
                f"- Disabling outcome: `{disable_status}`",
                f"- Initial failing tests: `{len(initial_baseline_result.failing_tests)}`",
                f"- Disabled generated test methods: `{len(disabled_tests or [])}`",
            ]
        )
        for test_id in disabled_tests or []:
            lines.append(f"- `{test_id}`")
    else:
        lines.extend(
            [
                "",
                "## Baseline-Failing Test Disabling",
                "- Disabling applied: `False`",
                f"- Disabling outcome: `{disable_status}`",
                "- Disabled generated test methods: `0`",
            ]
        )
    lines.extend(
        [
            "",
            "## Final Baseline Validation",
        ]
    )
    _append_maven_result(lines, baseline_result)
    lines.extend(
        [
            "",
            "## Coverage",
        ]
    )
    if baseline_coverage is None:
        lines.append("- JaCoCo report not found.")
    else:
        lines.extend(
            [
                f"- Instruction coverage: `{baseline_coverage.instruction_rate:.2%}`",
                f"- Line coverage: `{baseline_coverage.line_rate:.2%}`",
                f"- Branch coverage: `{baseline_coverage.branch_rate:.2%}`",
            ]
        )
    lines.extend(
        [
            "",
            "## PIT Mutation Testing",
        ]
    )
    if pitest_result is None:
        if baseline_result.passed:
            lines.append("- PIT result not available.")
        else:
            lines.append("- PIT was skipped because the final baseline test suite did not pass.")
    else:
        lines.extend(
            [
                f"- Exit code: `{pitest_result.exit_code}`",
                f"- Report file: `{pitest_result.report_file or 'not found'}`",
                f"- Total mutations: `{pitest_result.total_mutations}`",
            ]
        )
        for status, count in sorted(pitest_result.status_counts.items()):
            lines.append(f"- {status}: `{count}`")
    lines.extend(
        [
            "",
            "## Summary",
        ]
    )
    mutation_score = pitest_result.mutation_score if pitest_result is not None else None
    if mutation_score is None:
        lines.append("- Mutation score: `N/A`")
    else:
        lines.append(f"- Mutation score: `{mutation_score:.2%}`")
    if not baseline_result.passed:
        lines.extend(
            [
                "",
                "## Note",
                "- Baseline test validation did not pass.",
                "- PIT mutation testing requires a green baseline test suite, so mutation scoring was skipped.",
            ]
        )
    classification_names = [disable_status]
    if generated_tests is not None:
        classification_names.append(generated_tests.repair_outcome)
    repair_definitions = selected_definitions(REPAIR_CLASSIFICATIONS, classification_names)
    disabling_definitions = selected_definitions(DISABLING_CLASSIFICATIONS, classification_names)
    if repair_definitions or disabling_definitions:
        lines.extend(["", "## Classification Definitions"])
        for name, description in repair_definitions:
            lines.append(f"- `{name}`: {description}")
        for name, description in disabling_definitions:
            lines.append(f"- `{name}`: {description}")
    return "\n".join(lines)


def as_serializable_maven_result(result: MavenResult) -> dict[str, object]:
    return asdict(result)


def as_serializable_pitest_result(result: PitestResult | None) -> dict[str, object] | None:
    return asdict(result) if result is not None else None


def as_serializable_coverage(coverage: JacocoCoverage | None) -> dict[str, object] | None:
    if coverage is None:
        return None

    payload = asdict(coverage)
    payload["instruction_rate"] = coverage.instruction_rate
    payload["line_rate"] = coverage.line_rate
    payload["branch_rate"] = coverage.branch_rate
    return payload
