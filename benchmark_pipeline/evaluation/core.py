from __future__ import annotations

"""Evaluation orchestration for executing generated tests and PIT mutation analysis."""

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Sequence

from benchmark_pipeline.fs_utils import stage_repo_with_tests
from benchmark_pipeline.tools.maven import parse_jacoco_report, run_maven_command, run_maven_tests
from benchmark_pipeline.models import JacocoCoverage, MavenResult, PitestResult
from benchmark_pipeline.tools.pitest import persist_pitest_reports, run_pitest
from benchmark_pipeline.evaluation.test_cleaning import disable_baseline_failing_tests


@dataclass
class EvaluationOutcome:
    baseline_result: MavenResult
    baseline_coverage: JacocoCoverage | None
    pitest_result: PitestResult | None
    disabled_tests: list[str]
    initial_baseline_result: MavenResult | None = None


def evaluate_repositories(
    baseline_repo: Path,
    tests_dir: Path,
    maven_cmd: Sequence[str],
    pitest_report_dir: Path | None = None,
) -> EvaluationOutcome:
    staged_dirs: list[Path] = []
    try:
        staged_baseline = stage_repo_with_tests(baseline_repo, tests_dir)
        staged_dirs.append(staged_baseline)

        initial_baseline_result = run_maven_tests(staged_baseline, maven_cmd)
        baseline_result = initial_baseline_result
        disabled_tests: list[str] = []
        evaluated_stage = staged_baseline

        if initial_baseline_result.status == "test_failures" and initial_baseline_result.failing_tests:
            evaluated_stage = stage_repo_with_tests(baseline_repo, tests_dir)
            staged_dirs.append(evaluated_stage)
            disabled_tests = disable_baseline_failing_tests(
                evaluated_stage,
                initial_baseline_result.failing_tests,
            )
            baseline_result = run_maven_tests(evaluated_stage, maven_cmd)

        baseline_coverage = parse_jacoco_report(evaluated_stage / "target" / "site" / "jacoco" / "jacoco.xml")
        if baseline_coverage is None:
            run_maven_command(evaluated_stage, [maven_cmd[0], "jacoco:report", "-DskipTests"])
            baseline_coverage = parse_jacoco_report(
                evaluated_stage / "target" / "site" / "jacoco" / "jacoco.xml"
            )

        pitest_result = run_pitest(evaluated_stage, maven_cmd[0]) if baseline_result.passed else None
        if pitest_result is not None and pitest_report_dir is not None:
            persist_pitest_reports(pitest_result, pitest_report_dir)
        return EvaluationOutcome(
            baseline_result=baseline_result,
            baseline_coverage=baseline_coverage,
            pitest_result=pitest_result,
            disabled_tests=disabled_tests,
            initial_baseline_result=initial_baseline_result if disabled_tests else None,
        )
    finally:
        for staged_dir in staged_dirs:
            if staged_dir.exists():
                shutil.rmtree(staged_dir, ignore_errors=True)
