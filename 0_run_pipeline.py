from __future__ import annotations

"""CLI entrypoint for running the full benchmark pipeline end to end."""

import argparse
from pathlib import Path

from benchmark_pipeline.config import REPO_GEN_MODEL, TEST_GEN_MODEL
from benchmark_pipeline.pipeline import PipelineConfig, run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full repository -> tests -> PIT evaluation pipeline.")
    parser.add_argument("--model", default=None, help="Default model used when repo/test models are not set separately.")
    parser.add_argument("--repo-model", default=None, help="Model for baseline repo generation.")
    parser.add_argument("--tests-model", default=None, help="Model for test generation.")
    parser.add_argument("--project-name", default="generated-java-app", help="Suggested project name for baseline generation.")
    parser.add_argument("--baseline-repo", default="artifacts/baseline_repo", help="Baseline repository output directory.")
    parser.add_argument("--tests-dir", default="artifacts/generated_tests", help="Generated tests output directory.")
    parser.add_argument("--baseline-manifest", default="artifacts/manifests/baseline_repo.json", help="Manifest path for baseline generation.")
    parser.add_argument("--tests-manifest", default="artifacts/manifests/generated_tests.json", help="Manifest path for generated tests.")
    parser.add_argument("--report-json", default="artifacts/reports/evaluation_report.json", help="JSON report path for evaluation.")
    parser.add_argument("--report-md", default="artifacts/reports/evaluation_report.md", help="Markdown report path for evaluation.")
    parser.add_argument("--pitest-report-dir", default="artifacts/reports/pit-reports", help="Directory where PIT XML/HTML reports are copied after evaluation.")
    parser.add_argument("--maven-cmd", nargs="+", default=["mvn", "test"], help="Maven command used for baseline verification and evaluation.")
    parser.add_argument("--max-repairs", type=int, default=1, help="Maximum baseline repo repair attempts.")
    args = parser.parse_args()

    config = PipelineConfig(
        repo_model=args.repo_model or args.model or REPO_GEN_MODEL,
        tests_model=args.tests_model or args.model or TEST_GEN_MODEL,
        project_name=args.project_name,
        baseline_repo=Path(args.baseline_repo),
        tests_dir=Path(args.tests_dir),
        baseline_manifest=Path(args.baseline_manifest),
        tests_manifest=Path(args.tests_manifest),
        report_json=Path(args.report_json),
        report_md=Path(args.report_md),
        pitest_report_dir=Path(args.pitest_report_dir),
        maven_cmd=args.maven_cmd,
        max_repairs=args.max_repairs,
    )
    run_pipeline(config)


if __name__ == "__main__":
    main()
