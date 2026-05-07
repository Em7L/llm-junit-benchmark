from __future__ import annotations

"""Evaluation orchestration for executing tests and computing mutation results."""

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Sequence

from benchmark_pipeline.fs_utils import dump_json, stage_repo_with_tests
from benchmark_pipeline.maven import parse_jacoco_report, run_maven_command, run_maven_tests
from benchmark_pipeline.models import JacocoCoverage, MavenResult
from benchmark_pipeline.reports import as_serializable_coverage, as_serializable_maven_result


@dataclass
class EvaluationOutcome:
    baseline_result: MavenResult
    baseline_coverage: JacocoCoverage | None
    mutant_results: list[dict[str, object]]
    mutation_score: float | None

    @property
    def payload(self) -> dict[str, object]:
        payload = {
            "baseline_result": as_serializable_maven_result(self.baseline_result),
            "baseline_coverage": as_serializable_coverage(self.baseline_coverage),
            "mutant_results": self.mutant_results,
            "mutation_score": self.mutation_score,
        }
        return payload


def evaluate_repositories(
    baseline_repo: Path,
    tests_dir: Path,
    mutants_dir: Path,
    maven_cmd: Sequence[str],
) -> EvaluationOutcome:
    staged_dirs: list[Path] = []
    try:
        staged_baseline = stage_repo_with_tests(baseline_repo, tests_dir)
        staged_dirs.append(staged_baseline)

        baseline_result = run_maven_tests(staged_baseline, maven_cmd)
        baseline_coverage = parse_jacoco_report(staged_baseline / "target" / "site" / "jacoco" / "jacoco.xml")
        if baseline_coverage is None:
            run_maven_command(staged_baseline, [maven_cmd[0], "jacoco:report", "-DskipTests"])
            baseline_coverage = parse_jacoco_report(staged_baseline / "target" / "site" / "jacoco" / "jacoco.xml")

        baseline_failed_tests = set(baseline_result.failing_tests)

        mutant_results: list[dict[str, object]] = []
        mutant_dirs = sorted(path for path in mutants_dir.iterdir() if path.is_dir())
        for mutant_dir in mutant_dirs:
            staged_mutant = stage_repo_with_tests(mutant_dir, tests_dir)
            staged_dirs.append(staged_mutant)

            result = run_maven_tests(staged_mutant, maven_cmd)
            new_failing_tests = sorted(set(result.failing_tests) - baseline_failed_tests)
            killed = (not result.passed) if baseline_result.passed else bool(new_failing_tests)
            mutant_results.append(
                {
                    "mutant_id": mutant_dir.name,
                    "description": f"Mutant repo at {mutant_dir.as_posix()}",
                    "killed": killed,
                    "exit_code": result.exit_code,
                    "tests": result.tests,
                    "failures": result.failures,
                    "errors": result.errors,
                    "skipped": result.skipped,
                    "failing_tests": result.failing_tests,
                    "new_failing_tests": new_failing_tests,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )

        mutation_score = sum(1 for item in mutant_results if item["killed"]) / len(mutant_results) if mutant_results else 0.0
        return EvaluationOutcome(
            baseline_result=baseline_result,
            baseline_coverage=baseline_coverage,
            mutant_results=mutant_results,
            mutation_score=mutation_score,
        )
    finally:
        for staged_dir in staged_dirs:
            if staged_dir.exists():
                shutil.rmtree(staged_dir, ignore_errors=True)


def write_evaluation_json(report_json: Path, outcome: EvaluationOutcome) -> None:
    dump_json(report_json, outcome.payload)
