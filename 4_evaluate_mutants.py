from __future__ import annotations

"""CLI entrypoint for evaluating generated tests with JaCoCo and PIT."""

import argparse
from pathlib import Path

from benchmark_pipeline.evaluation import evaluate_repositories, write_evaluation_json
from benchmark_pipeline.reports import markdown_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run generated JUnit tests against the baseline and evaluate them with PIT.")
    parser.add_argument("--baseline-repo", default="artifacts/baseline_repo", help="Path to the baseline repository.")
    parser.add_argument("--tests-dir", default="artifacts/generated_tests", help="Path to the generated test files.")
    parser.add_argument("--report-json", default="artifacts/reports/evaluation_report.json", help="Path to the JSON report.")
    parser.add_argument("--report-md", default="artifacts/reports/evaluation_report.md", help="Path to the Markdown report.")
    parser.add_argument("--pitest-report-dir", default="artifacts/reports/pit-reports", help="Directory where PIT XML/HTML reports are copied after evaluation.")
    parser.add_argument("--maven-cmd", nargs="+", default=["mvn", "test"], help="Command used to run Maven tests.")
    args = parser.parse_args()

    baseline_repo = Path(args.baseline_repo)
    tests_dir = Path(args.tests_dir)

    if not baseline_repo.exists():
        raise FileNotFoundError(f"Baseline repository not found: {baseline_repo}")
    if not tests_dir.exists():
        raise FileNotFoundError(f"Tests directory not found: {tests_dir}")

    print()
    print("-" * 72)
    print("[evaluation] PIT mutation evaluation")
    print("-" * 72)
    print(f"[evaluation] Baseline repository: {baseline_repo.resolve()}")
    print(f"[evaluation] Generated tests: {tests_dir.resolve()}")
    print(f"[evaluation] Running Maven verification with: {' '.join(args.maven_cmd)}")
    outcome = evaluate_repositories(
        baseline_repo=baseline_repo,
        tests_dir=tests_dir,
        maven_cmd=args.maven_cmd,
        pitest_report_dir=Path(args.pitest_report_dir),
    )
    print(f"[evaluation] Writing JSON report to {Path(args.report_json).resolve()}")
    write_evaluation_json(Path(args.report_json), outcome)
    Path(args.report_md).parent.mkdir(parents=True, exist_ok=True)
    print(f"[evaluation] Writing markdown report to {Path(args.report_md).resolve()}")
    Path(args.report_md).write_text(
        markdown_report(
            outcome.baseline_result,
            outcome.baseline_coverage,
            outcome.pitest_result,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Baseline repo passed: {outcome.baseline_result.passed}")
    print(f"Baseline run status: {outcome.baseline_result.status}")
    if outcome.baseline_coverage is not None:
        print(f"Line coverage: {outcome.baseline_coverage.line_rate:.2%}")
        print(f"Branch coverage: {outcome.baseline_coverage.branch_rate:.2%}")
    mutation_score = outcome.pitest_result.mutation_score if outcome.pitest_result is not None else None
    if mutation_score is None:
        print("Mutation score: N/A")
    else:
        print(f"Mutation score: {mutation_score:.2%}")
    print(f"JSON report: {Path(args.report_json).resolve()}")
    print(f"Markdown report: {Path(args.report_md).resolve()}")


if __name__ == "__main__":
    main()
