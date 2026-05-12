from __future__ import annotations

"""Report-formatting helpers for serializing and rendering evaluation results."""

from dataclasses import asdict

from benchmark_pipeline.models import JacocoCoverage, MavenResult, PitestResult


def markdown_report(
    baseline_result: MavenResult,
    baseline_coverage: JacocoCoverage | None,
    pitest_result: PitestResult | None,
    disabled_tests: list[str] | None = None,
    initial_baseline_result: MavenResult | None = None,
) -> str:
    lines = [
        "# Mutation Evaluation Report",
        "",
        "## Baseline Repository",
        f"- Passed: `{baseline_result.passed}`",
        f"- Run status: `{baseline_result.status}`",
        f"- Exit code: `{baseline_result.exit_code}`",
        f"- Tests: `{baseline_result.tests}`",
        f"- Failures: `{baseline_result.failures}`",
        f"- Errors: `{baseline_result.errors}`",
        f"- Skipped: `{baseline_result.skipped}`",
    ]
    if baseline_result.status_reason:
        lines.append(f"- Status reason: {baseline_result.status_reason}")
    if baseline_result.failing_tests:
        lines.append(f"- Baseline failing tests: `{len(baseline_result.failing_tests)}`")
    if initial_baseline_result is not None:
        lines.extend(
            [
                "",
                "## Baseline Test Cleaning",
                f"- Initial run status: `{initial_baseline_result.status}`",
                f"- Initial failing tests: `{len(initial_baseline_result.failing_tests)}`",
                f"- Disabled generated test methods: `{len(disabled_tests or [])}`",
            ]
        )
        for test_id in disabled_tests or []:
            lines.append(f"- `{test_id}`")
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
