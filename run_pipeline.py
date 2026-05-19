from __future__ import annotations

"""CLI entrypoint for running the full benchmark pipeline end to end."""

import argparse
from pathlib import Path

from benchmark_pipeline.config import REPO_GEN_MODEL, TEST_GEN_MODEL
from benchmark_pipeline.generation import BENCHMARK_PROFILE_IDS, get_benchmark_profile
from benchmark_pipeline.pipeline import PipelineConfig, run_pipeline, safe_model_name


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full repository -> tests -> PIT evaluation pipeline.")
    parser.add_argument("--model", default=None, help="Default model used when repo/test models are not set separately.")
    parser.add_argument("--repo-model", default=None, help="Model for baseline repo generation.")
    parser.add_argument("--tests-model", default=None, help="Single model for test generation.")
    parser.add_argument("--tests-models", nargs="+", default=None, help="One or more models for test generation.")
    parser.add_argument(
        "--profile-id",
        choices=BENCHMARK_PROFILE_IDS,
        default=None,
        help="Optional benchmark profile used for baseline repository generation.",
    )
    parser.add_argument("--project-name", default="generated-java-app", help="Suggested project name for baseline generation.")
    parser.add_argument("--output-root", default="run_outputs/runs", help="Root directory for preserved pipeline run outputs.")
    parser.add_argument("--run-dir", default=None, help="Explicit run directory. Defaults to the next run-N directory under --output-root.")
    parser.add_argument("--baseline-repo", default=None, help="Baseline repository output directory.")
    parser.add_argument("--tests-dir", default=None, help="Generated tests output directory.")
    parser.add_argument("--baseline-manifest", default=None, help="Manifest path for baseline generation.")
    parser.add_argument("--tests-manifest", default=None, help="Manifest path for generated tests.")
    parser.add_argument("--report-json", default=None, help="JSON path for the comparison report.")
    parser.add_argument("--report-md", default=None, help="Markdown path for the comparison report.")
    parser.add_argument("--pitest-report-dir", default=None, help="Directory where PIT XML/HTML reports are copied after evaluation.")
    parser.add_argument("--maven-cmd", nargs="+", default=["mvn", "test"], help="Maven command used for baseline verification and evaluation.")
    parser.add_argument("--max-repairs", type=int, default=1, help="Maximum repository and test-suite repair attempts.")
    args = parser.parse_args()

    default_model = args.model or TEST_GEN_MODEL
    tests_models = args.tests_models or [args.tests_model or default_model]

    repo_model = args.repo_model or args.model or REPO_GEN_MODEL
    benchmark_profile = get_benchmark_profile(args.profile_id) if args.profile_id else None
    run_dir = (
        Path(args.run_dir)
        if args.run_dir
        else next_run_dir(Path(args.output_root), benchmark_profile.profile_id if benchmark_profile else None, repo_model, tests_models)
    )
    config = PipelineConfig(
        repo_model=repo_model,
        tests_models=tuple(tests_models),
        benchmark_profile=benchmark_profile,
        project_name=args.project_name,
        baseline_repo=Path(args.baseline_repo) if args.baseline_repo else run_dir / "baseline_repo",
        tests_dir=Path(args.tests_dir) if args.tests_dir else run_dir / "generated_tests",
        profile_manifest=run_dir / "manifests/benchmark_profile.json",
        baseline_manifest=Path(args.baseline_manifest) if args.baseline_manifest else run_dir / "manifests/baseline_repo.json",
        tests_manifest=Path(args.tests_manifest) if args.tests_manifest else run_dir / "manifests/generated_tests.json",
        report_json=Path(args.report_json) if args.report_json else run_dir / "reports/comparison_report.json",
        report_md=Path(args.report_md) if args.report_md else run_dir / "reports/comparison_report.md",
        pitest_report_dir=Path(args.pitest_report_dir) if args.pitest_report_dir else run_dir / "reports/pit-reports",
        maven_cmd=args.maven_cmd,
        max_repairs=args.max_repairs,
    )
    run_pipeline(config)


def next_run_dir(output_root: Path, profile_id: str | None, repo_model: str, tests_models: list[str]) -> Path:
    group_dir = output_root / run_group_name(profile_id, repo_model, tests_models)
    index = 1
    while True:
        candidate = group_dir / f"run-{index:03d}"
        if not candidate.exists():
            return candidate
        index += 1


def run_group_name(profile_id: str | None, repo_model: str, tests_models: list[str]) -> str:
    tests_part = "_".join(sorted(safe_model_name(model) for model in tests_models))
    return (
        f"profile-{safe_model_name(profile_id or 'auto')}__repo-{safe_model_name(repo_model)}__tests-{tests_part}"
    )


if __name__ == "__main__":
    main()
