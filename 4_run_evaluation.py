from __future__ import annotations

import argparse
from pathlib import Path

from pipeline_common import (
    as_serializable_coverage,
    as_serializable_maven_result,
    dump_json,
    markdown_report,
    parse_jacoco_report,
    run_maven_command,
    run_maven_tests,
    stage_repo_with_tests,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Agent 2 tests against the baseline and mutant repositories.")
    parser.add_argument("--baseline-repo", default="artifacts/baseline_repo", help="Path to the baseline repository.")
    parser.add_argument("--tests-dir", default="artifacts/generated_tests", help="Path to the generated test files.")
    parser.add_argument("--mutants-dir", default="artifacts/mutants", help="Path to the generated mutant repositories.")
    parser.add_argument("--report-json", default="artifacts/reports/evaluation_report.json", help="Path to the JSON report.")
    parser.add_argument("--report-md", default="artifacts/reports/evaluation_report.md", help="Path to the Markdown report.")
    parser.add_argument("--maven-cmd", nargs="+", default=["mvn", "test"], help="Command used to run Maven tests.")
    args = parser.parse_args()

    baseline_repo = Path(args.baseline_repo)
    tests_dir = Path(args.tests_dir)
    mutants_dir = Path(args.mutants_dir)

    if not baseline_repo.exists():
        raise FileNotFoundError(f"Baseline repository not found: {baseline_repo}")
    if not tests_dir.exists():
        raise FileNotFoundError(f"Tests directory not found: {tests_dir}")
    if not mutants_dir.exists():
        raise FileNotFoundError(f"Mutants directory not found: {mutants_dir}")

    staged_baseline = stage_repo_with_tests(baseline_repo, tests_dir)
    baseline_result = run_maven_tests(staged_baseline, args.maven_cmd)
    baseline_coverage = parse_jacoco_report(staged_baseline / "target" / "site" / "jacoco" / "jacoco.xml")
    if baseline_coverage is None:
        run_maven_command(staged_baseline, [args.maven_cmd[0], "jacoco:report", "-DskipTests"])
        baseline_coverage = parse_jacoco_report(staged_baseline / "target" / "site" / "jacoco" / "jacoco.xml")

    if not baseline_result.passed:
        payload = {
            "baseline_result": as_serializable_maven_result(baseline_result),
            "baseline_coverage": as_serializable_coverage(baseline_coverage),
            "mutant_results": [],
            "mutation_score": None,
            "status": "invalid_baseline",
            "message": "Baseline repository failed before mutant evaluation. Mutation score is not valid for this run.",
        }
        dump_json(Path(args.report_json), payload)
        Path(args.report_md).parent.mkdir(parents=True, exist_ok=True)
        report_lines = [
            "# Mutation Evaluation Report",
            "",
            "## Baseline Repository",
            f"- Passed: `{baseline_result.passed}`",
            f"- Exit code: `{baseline_result.exit_code}`",
            f"- Tests: `{baseline_result.tests}`",
            f"- Failures: `{baseline_result.failures}`",
            f"- Errors: `{baseline_result.errors}`",
            f"- Skipped: `{baseline_result.skipped}`",
            "",
            "## Coverage",
        ]
        if baseline_coverage is None:
            report_lines.append("- JaCoCo report not found.")
        else:
            report_lines.extend(
                [
                    f"- Instruction coverage: `{baseline_coverage.instruction_rate:.2%}`",
                    f"- Line coverage: `{baseline_coverage.line_rate:.2%}`",
                    f"- Branch coverage: `{baseline_coverage.branch_rate:.2%}`",
                ]
            )
        report_lines.extend(
            [
                "",
                "## Status",
                "- Baseline repository failed before mutant evaluation.",
                "- Mutation score is invalid for this run.",
                "- Fix the baseline first, then rerun the evaluation.",
            ]
        )
        Path(args.report_md).write_text(
            "\n".join(report_lines),
            encoding="utf-8",
        )
        print("Baseline repo passed: False")
        print("Mutation evaluation aborted: baseline failed.")
        print(f"JSON report: {Path(args.report_json).resolve()}")
        print(f"Markdown report: {Path(args.report_md).resolve()}")
        return

    mutant_results: list[dict[str, object]] = []
    mutant_dirs = sorted(path for path in mutants_dir.iterdir() if path.is_dir())
    for mutant_dir in mutant_dirs:
        staged_mutant = stage_repo_with_tests(mutant_dir, tests_dir)
        result = run_maven_tests(staged_mutant, args.maven_cmd)
        mutant_results.append(
            {
                "mutant_id": mutant_dir.name,
                "description": f"Mutant repo at {mutant_dir.as_posix()}",
                "killed": not result.passed,
                "exit_code": result.exit_code,
                "tests": result.tests,
                "failures": result.failures,
                "errors": result.errors,
                "skipped": result.skipped,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )

    mutation_score = (
        sum(1 for item in mutant_results if item["killed"]) / len(mutant_results) if mutant_results else 0.0
    )

    payload = {
        "baseline_result": as_serializable_maven_result(baseline_result),
        "baseline_coverage": as_serializable_coverage(baseline_coverage),
        "mutant_results": mutant_results,
        "mutation_score": mutation_score,
    }
    dump_json(Path(args.report_json), payload)
    Path(args.report_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_md).write_text(
        markdown_report(baseline_result, baseline_coverage, mutant_results, mutation_score),
        encoding="utf-8",
    )

    print(f"Baseline repo passed: {baseline_result.passed}")
    if baseline_coverage is not None:
        print(f"Line coverage: {baseline_coverage.line_rate:.2%}")
        print(f"Branch coverage: {baseline_coverage.branch_rate:.2%}")
    print(f"Mutation score: {mutation_score:.2%}")
    print(f"JSON report: {Path(args.report_json).resolve()}")
    print(f"Markdown report: {Path(args.report_md).resolve()}")


if __name__ == "__main__":
    main()
