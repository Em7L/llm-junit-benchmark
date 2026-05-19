from __future__ import annotations

"""Run the thesis experiment matrix across benchmark profiles and model combinations."""

import argparse
import json
from pathlib import Path
import shutil
import time
from typing import Sequence

from benchmark_pipeline.generation import BENCHMARK_PROFILE_IDS, get_benchmark_profile
from benchmark_pipeline.pipeline import PipelineConfig, run_pipeline
from run_pipeline import next_run_dir, run_group_name


DEFAULT_REPO_MODELS: tuple[str, ...] = (
    "gpt-5.4-mini",
    "deepseek-v4-flash",
)

DEFAULT_TEST_MODELS: tuple[str, ...] = (
    "gpt-5.4-mini",
    "deepseek-v4-flash",
    "gemini-3-flash-preview",
    "gpt-4o-mini",
)

DEFAULT_REPETITIONS = 8
TIMING_SUMMARY_PATH = Path("experiment_timing_summary.json")


class ExperimentCondition(tuple[str, str]):
    __slots__ = ()

    def __new__(cls, profile_id: str, repo_model: str) -> "ExperimentCondition":
        return tuple.__new__(cls, (profile_id, repo_model))

    @property
    def profile_id(self) -> str:
        return self[0]

    @property
    def repo_model(self) -> str:
        return self[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the full thesis experiment matrix with preserved benchmark pipeline runs."
    )
    parser.add_argument(
        "--profile-ids",
        nargs="+",
        choices=BENCHMARK_PROFILE_IDS,
        default=list(BENCHMARK_PROFILE_IDS),
        help="Benchmark profiles to include in the matrix.",
    )
    parser.add_argument(
        "--repo-models",
        nargs="+",
        default=list(DEFAULT_REPO_MODELS),
        help="Repository-generation models to include in the matrix.",
    )
    parser.add_argument(
        "--tests-models",
        nargs="+",
        default=list(DEFAULT_TEST_MODELS),
        help="Fixed test-generation model set used for each experiment run.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=DEFAULT_REPETITIONS,
        help="Target number of preserved runs per profile/repo-model condition.",
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/runs",
        help="Root directory containing preserved pipeline runs.",
    )
    parser.add_argument(
        "--project-name",
        default="generated-java-app",
        help="Suggested project name for baseline generation.",
    )
    parser.add_argument(
        "--maven-cmd",
        nargs="+",
        default=["mvn", "test"],
        help="Maven command used for baseline verification and evaluation.",
    )
    parser.add_argument(
        "--max-repairs",
        type=int,
        default=1,
        help="Maximum repository and test-suite repair attempts per pipeline run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the experiment plan without executing any pipeline runs.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue with later conditions if one pipeline run fails.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_root = Path(args.output_root)
    tests_models = tuple(args.tests_models)
    conditions = [
        ExperimentCondition(profile_id=profile_id, repo_model=repo_model)
        for profile_id in args.profile_ids
        for repo_model in args.repo_models
    ]

    if args.repetitions < 1:
        raise ValueError("--repetitions must be at least 1.")
    if not tests_models:
        raise ValueError("At least one test-generation model must be provided.")

    print()
    print("=" * 72)
    print("[experiment] Thesis experiment matrix")
    print(f"[experiment] Conditions: {len(conditions)}")
    print(f"[experiment] Target repetitions per condition: {args.repetitions}")
    print(f"[experiment] Test-generation set: {', '.join(tests_models)}")
    print(f"[experiment] Output root: {output_root.resolve()}")
    print("=" * 72)

    failures: list[str] = []
    planned_runs = 0
    run_timings: list[dict[str, object]] = []
    matrix_started_at = time.time()

    for condition in conditions:
        existing_runs = count_existing_runs(output_root, condition, tests_models)
        remaining_runs = max(0, args.repetitions - existing_runs)
        group_name = run_group_name(condition.profile_id, condition.repo_model, list(tests_models))
        print(
            f"[experiment] Condition profile={condition.profile_id} repo={condition.repo_model}: "
            f"{existing_runs}/{args.repetitions} preserved runs"
        )
        if remaining_runs == 0:
            print(f"[experiment] Skipping {group_name}; target already satisfied.")
            continue

        planned_runs += remaining_runs
        for _ in range(remaining_runs):
            run_dir = next_run_dir(output_root, condition.profile_id, condition.repo_model, list(tests_models))
            print(f"[experiment] Planned run: {run_dir.resolve()}")
            if args.dry_run:
                continue

            config = build_pipeline_config(
                run_dir=run_dir,
                condition=condition,
                tests_models=tests_models,
                project_name=args.project_name,
                maven_cmd=args.maven_cmd,
                max_repairs=args.max_repairs,
            )
            run_started_at = time.time()
            try:
                run_pipeline(config)
                duration_seconds = time.time() - run_started_at
                run_timings.append(
                    run_timing_record(
                        condition=condition,
                        run_dir=run_dir,
                        duration_seconds=duration_seconds,
                        status="completed",
                    )
                )
                print(
                    f"[experiment] Completed {run_dir.name} in {format_duration(duration_seconds)}"
                )
            except Exception as exc:
                duration_seconds = time.time() - run_started_at
                if is_provider_limit_error(exc):
                    cleanup_invalid_run(run_dir)
                    run_timings.append(
                        run_timing_record(
                            condition=condition,
                            run_dir=run_dir,
                            duration_seconds=duration_seconds,
                            status="aborted_provider_limit",
                        )
                    )
                    write_timing_summary(
                        output_root=output_root,
                        summary=build_timing_summary(
                            conditions=conditions,
                            planned_runs=planned_runs,
                            failures=failures,
                            run_timings=run_timings,
                            total_duration_seconds=time.time() - matrix_started_at,
                            dry_run=args.dry_run,
                        ),
                    )
                    print(
                        "[experiment] Run aborted due to provider limit/quota issue. "
                        f"Deleted invalid run directory: {run_dir.resolve()}. "
                        f"Elapsed before abort: {format_duration(duration_seconds)}"
                    )
                    raise
                message = (
                    f"profile={condition.profile_id} repo={condition.repo_model} run={run_dir.name}: {exc}"
                )
                failures.append(message)
                run_timings.append(
                    run_timing_record(
                        condition=condition,
                        run_dir=run_dir,
                        duration_seconds=duration_seconds,
                        status="failed",
                    )
                )
                print(f"[experiment] Run failed: {message}")
                print(f"[experiment] Failed after {format_duration(duration_seconds)}")
                if not args.continue_on_error:
                    write_timing_summary(
                        output_root=output_root,
                        summary=build_timing_summary(
                            conditions=conditions,
                            planned_runs=planned_runs,
                            failures=failures,
                            run_timings=run_timings,
                            total_duration_seconds=time.time() - matrix_started_at,
                            dry_run=args.dry_run,
                        ),
                    )
                    raise

    total_duration_seconds = time.time() - matrix_started_at
    write_timing_summary(
        output_root=output_root,
        summary=build_timing_summary(
            conditions=conditions,
            planned_runs=planned_runs,
            failures=failures,
            run_timings=run_timings,
            total_duration_seconds=total_duration_seconds,
            dry_run=args.dry_run,
        ),
    )
    print()
    print("=" * 72)
    print("[experiment] Matrix run complete")
    print(f"[experiment] Planned missing runs: {planned_runs}")
    print(f"[experiment] Failures: {len(failures)}")
    print(f"[experiment] Executed runs: {len(run_timings)}")
    print(f"[experiment] Total elapsed: {format_duration(total_duration_seconds)}")
    print(f"[experiment] Timing summary: {(output_root / TIMING_SUMMARY_PATH).resolve()}")
    print("=" * 72)
    if failures:
        for failure in failures:
            print(f"[experiment] Failure detail: {failure}")


def build_pipeline_config(
    *,
    run_dir: Path,
    condition: ExperimentCondition,
    tests_models: Sequence[str],
    project_name: str,
    maven_cmd: Sequence[str],
    max_repairs: int,
) -> PipelineConfig:
    return PipelineConfig(
        repo_model=condition.repo_model,
        tests_models=tuple(tests_models),
        benchmark_profile=get_benchmark_profile(condition.profile_id),
        project_name=project_name,
        baseline_repo=run_dir / "baseline_repo",
        tests_dir=run_dir / "generated_tests",
        profile_manifest=run_dir / "manifests/benchmark_profile.json",
        baseline_manifest=run_dir / "manifests/baseline_repo.json",
        tests_manifest=run_dir / "manifests/generated_tests.json",
        report_json=run_dir / "reports/comparison_report.json",
        report_md=run_dir / "reports/comparison_report.md",
        pitest_report_dir=run_dir / "reports/pit-reports",
        maven_cmd=list(maven_cmd),
        max_repairs=max_repairs,
    )


def count_existing_runs(output_root: Path, condition: ExperimentCondition, tests_models: Sequence[str]) -> int:
    group_dir = output_root / run_group_name(condition.profile_id, condition.repo_model, list(tests_models))
    if not group_dir.exists():
        return 0
    return sum(1 for path in group_dir.iterdir() if path.is_dir() and path.name.startswith("run-"))


def cleanup_invalid_run(run_dir: Path) -> None:
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)


def is_provider_limit_error(exc: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if message_looks_like_limit_error(str(current)):
            return True
        current = current.__cause__ or current.__context__
    return False


def message_looks_like_limit_error(message: str) -> bool:
    normalized = " ".join(message.lower().split())
    patterns = (
        "insufficient_quota",
        "quota exceeded",
        "quota reached",
        "credit balance",
        "no credits",
        "out of credits",
        "billing",
        "rate limit",
        "rate-limit",
        "too many requests",
        "resource exhausted",
        "limit reached",
        "token limit",
    )
    return any(pattern in normalized for pattern in patterns)


def run_timing_record(
    *,
    condition: ExperimentCondition,
    run_dir: Path,
    duration_seconds: float,
    status: str,
) -> dict[str, object]:
    return {
        "profile_id": condition.profile_id,
        "repo_model": condition.repo_model,
        "run_dir": run_dir.as_posix(),
        "run_name": run_dir.name,
        "status": status,
        "duration_seconds": round(duration_seconds, 3),
        "duration_hms": format_duration(duration_seconds),
    }


def build_timing_summary(
    *,
    conditions: Sequence[ExperimentCondition],
    planned_runs: int,
    failures: Sequence[str],
    run_timings: Sequence[dict[str, object]],
    total_duration_seconds: float,
    dry_run: bool,
) -> dict[str, object]:
    return {
        "condition_count": len(conditions),
        "planned_missing_runs": planned_runs,
        "executed_runs": len(run_timings),
        "failure_count": len(failures),
        "failures": list(failures),
        "dry_run": dry_run,
        "total_duration_seconds": round(total_duration_seconds, 3),
        "total_duration_hms": format_duration(total_duration_seconds),
        "runs": list(run_timings),
    }


def write_timing_summary(*, output_root: Path, summary: dict[str, object]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / TIMING_SUMMARY_PATH).write_text(json.dumps(summary, indent=2), encoding="utf-8")


def format_duration(duration_seconds: float) -> str:
    total_seconds = max(0, int(round(duration_seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


if __name__ == "__main__":
    main()
