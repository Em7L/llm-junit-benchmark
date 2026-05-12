from __future__ import annotations

"""CLI entrypoint for running the full benchmark pipeline end to end."""

import argparse
import subprocess
import sys
from pathlib import Path

from benchmark_pipeline.config import DEFAULT_MODEL


def run_step(label: str, command: list[str]) -> None:
    print()
    print("=" * 72)
    print(f"[pipeline] Starting {label}")
    print(f"[pipeline] Command: {' '.join(command)}")
    print("=" * 72)
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        print()
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")
    print(f"[pipeline] Completed {label}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full repository -> tests -> PIT evaluation pipeline.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to run the pipeline scripts.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Default model passed to generation scripts.")
    parser.add_argument("--repo-model", default=None, help="Optional override model for baseline repo generation.")
    parser.add_argument("--tests-model", default=None, help="Optional override model for test generation.")
    parser.add_argument("--project-name", default="generated-java-app", help="Suggested project name for baseline generation.")
    parser.add_argument("--baseline-repo", default="artifacts/baseline_repo", help="Baseline repository output directory.")
    parser.add_argument("--tests-dir", default="artifacts/generated_tests", help="Generated tests output directory.")
    parser.add_argument("--baseline-manifest", default="artifacts/manifests/baseline_repo.json", help="Manifest path for baseline generation.")
    parser.add_argument("--tests-manifest", default="artifacts/manifests/generated_tests.json", help="Manifest path for generated tests.")
    parser.add_argument("--report-json", default="artifacts/reports/evaluation_report.json", help="JSON report path for evaluation.")
    parser.add_argument("--report-md", default="artifacts/reports/evaluation_report.md", help="Markdown report path for evaluation.")
    parser.add_argument("--maven-cmd", nargs="+", default=["mvn", "test"], help="Maven command used for baseline verification and evaluation.")
    parser.add_argument("--max-repairs", type=int, default=2, help="Maximum baseline repo repair attempts.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    python_executable = args.python
    repo_model = args.repo_model or args.model
    tests_model = args.tests_model or args.model

    print()
    print("=" * 72)
    print("[pipeline] Running full benchmark pipeline")
    print(f"[pipeline] Root: {root}")
    print(f"[pipeline] Default model: {args.model}")
    print("=" * 72)

    run_step(
        "baseline generation",
        [
            python_executable,
            str(root / "1_generate_baseline_repo.py"),
            "--output-dir",
            args.baseline_repo,
            "--model",
            repo_model,
            "--project-name",
            args.project_name,
            "--manifest",
            args.baseline_manifest,
            "--verify-cmd",
            *args.maven_cmd,
            "--max-repairs",
            str(args.max_repairs),
        ],
    )
    run_step(
        "test generation",
        [
            python_executable,
            str(root / "2_generate_tests.py"),
            "--repo-dir",
            args.baseline_repo,
            "--output-dir",
            args.tests_dir,
            "--model",
            tests_model,
            "--manifest",
            args.tests_manifest,
        ],
    )
    run_step(
        "PIT evaluation",
        [
            python_executable,
            str(root / "4_evaluate_mutants.py"),
            "--baseline-repo",
            args.baseline_repo,
            "--tests-dir",
            args.tests_dir,
            "--report-json",
            args.report_json,
            "--report-md",
            args.report_md,
            "--maven-cmd",
            *args.maven_cmd,
        ],
    )

    print()
    print("[pipeline] Full pipeline completed successfully")


if __name__ == "__main__":
    main()
