from __future__ import annotations

"""CLI entrypoint for evaluating generated tests with JaCoCo and PIT."""

import argparse
from pathlib import Path

from benchmark_pipeline.evaluation.comparison_reports import write_comparison_reports
from benchmark_pipeline.evaluation.runner import EvaluationRunConfig, run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run generated JUnit tests against the baseline and evaluate them with PIT.")
    parser.add_argument("--baseline-repo", default="artifacts/baseline_repo", help="Path to the baseline repository.")
    parser.add_argument("--tests-dir", default="artifacts/generated_tests", help="Path to one generated test suite, or a directory containing multiple suite subdirectories.")
    parser.add_argument("--report-json", default="artifacts/reports/comparison_report.json", help="Path used to place the comparison JSON report.")
    parser.add_argument("--report-md", default="artifacts/reports/comparison_report.md", help="Path used to place the comparison Markdown report.")
    parser.add_argument("--pitest-report-dir", default="artifacts/reports/pit-reports", help="Directory where PIT XML/HTML reports are copied after evaluation.")
    parser.add_argument("--maven-cmd", nargs="+", default=["mvn", "test"], help="Command used to run Maven tests.")
    args = parser.parse_args()

    runs = run_evaluation(
        EvaluationRunConfig(
            baseline_repo=Path(args.baseline_repo),
            tests_dir=Path(args.tests_dir),
            pitest_report_dir=Path(args.pitest_report_dir),
            maven_cmd=args.maven_cmd,
        )
    )
    suite_names = {run.suite_name: run.suite_name for run in runs}
    write_comparison_reports(
        repo_model="standalone-evaluation",
        tests_models=[run.suite_name for run in runs],
        suite_names=suite_names,
        baseline_repo=Path(args.baseline_repo),
        report_json=Path(args.report_json),
        report_md=Path(args.report_md),
        generated_tests={},
        test_generation_errors={},
        evaluations=runs,
        initial_evaluations={},
    )


if __name__ == "__main__":
    main()

