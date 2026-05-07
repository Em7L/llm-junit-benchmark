from __future__ import annotations

"""Report-formatting helpers for serializing and rendering evaluation results."""

from dataclasses import asdict

from benchmark_pipeline.models import JacocoCoverage, MavenResult


def markdown_report(
    baseline_result: MavenResult,
    baseline_coverage: JacocoCoverage | None,
    mutant_results: list[dict[str, object]],
    mutation_score: float,
) -> str:
    lines = [
        "# Mutation Evaluation Report",
        "",
        "## Baseline Repository",
        f"- Passed: `{baseline_result.passed}`",
        f"- Exit code: `{baseline_result.exit_code}`",
        f"- Tests: `{baseline_result.tests}`",
        f"- Failures: `{baseline_result.failures}`",
        f"- Errors: `{baseline_result.errors}`",
        f"- Skipped: `{baseline_result.skipped}`",
    ]
    if baseline_result.failing_tests:
        lines.append(f"- Baseline failing tests: `{len(baseline_result.failing_tests)}`")
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
            "## Mutants",
        ]
    )
    for result in mutant_results:
        extra = ""
        if result.get("new_failing_tests"):
            extra = f" new_failures=`{len(result['new_failing_tests'])}`"
        lines.extend(
            [
                f"- `{result['mutant_id']}`: killed=`{result['killed']}` exit_code=`{result['exit_code']}` failures=`{result['failures']}` errors=`{result['errors']}`{extra}",
                f"  description: {result['description']}",
            ]
        )
        if result.get("new_failing_tests"):
            lines.append(f"  new failing tests: {', '.join(result['new_failing_tests'])}")
    lines.extend(
        [
            "",
            "## Summary",
            f"- Mutation score: `{mutation_score:.2%}`",
            f"- Mutants killed: `{sum(1 for item in mutant_results if item['killed'])}/{len(mutant_results)}`",
        ]
    )
    if not baseline_result.passed:
        lines.extend(
            [
                "",
                "## Note",
                "- Baseline tests already had failures.",
                "- Mutants are counted as killed only when they introduce new failing tests beyond the baseline failure set.",
            ]
        )
    return "\n".join(lines)


def as_serializable_maven_result(result: MavenResult) -> dict[str, object]:
    return asdict(result)


def as_serializable_coverage(coverage: JacocoCoverage | None) -> dict[str, object] | None:
    if coverage is None:
        return None

    payload = asdict(coverage)
    payload["instruction_rate"] = coverage.instruction_rate
    payload["line_rate"] = coverage.line_rate
    payload["branch_rate"] = coverage.branch_rate
    return payload
