from __future__ import annotations

"""CLI entrypoint for running generated tests against the baseline and mutant repositories."""

import argparse
from pathlib import Path

from benchmark_pipeline.evaluation import evaluate_repositories, write_evaluation_json
from benchmark_pipeline.reports import markdown_report


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

    print()
    print("-" * 72)
    print("[evaluation] Mutation evaluation")
    print("-" * 72)
    print(f"[evaluation] Baseline repository: {baseline_repo.resolve()}")
    print(f"[evaluation] Generated tests: {tests_dir.resolve()}")
    print(f"[evaluation] Mutants directory: {mutants_dir.resolve()}")
    print(f"[evaluation] Running Maven verification with: {' '.join(args.maven_cmd)}")
    outcome = evaluate_repositories(
        baseline_repo=baseline_repo,
        tests_dir=tests_dir,
        mutants_dir=mutants_dir,
        maven_cmd=args.maven_cmd,
    )
    print(f"[evaluation] Writing JSON report to {Path(args.report_json).resolve()}")
    write_evaluation_json(Path(args.report_json), outcome)
    Path(args.report_md).parent.mkdir(parents=True, exist_ok=True)
    print(f"[evaluation] Writing markdown report to {Path(args.report_md).resolve()}")
    Path(args.report_md).write_text(
        markdown_report(
            outcome.baseline_result,
            outcome.baseline_coverage,
            outcome.mutant_results,
            outcome.mutation_score,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Baseline repo passed: {outcome.baseline_result.passed}")
    if outcome.baseline_coverage is not None:
        print(f"Line coverage: {outcome.baseline_coverage.line_rate:.2%}")
        print(f"Branch coverage: {outcome.baseline_coverage.branch_rate:.2%}")
    print(f"Mutation score: {outcome.mutation_score:.2%}")
    print(f"JSON report: {Path(args.report_json).resolve()}")
    print(f"Markdown report: {Path(args.report_md).resolve()}")


if __name__ == "__main__":
    main()
