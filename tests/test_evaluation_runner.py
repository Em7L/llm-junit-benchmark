from __future__ import annotations

import shutil
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from benchmark_pipeline.evaluation import EvaluationOutcome
from benchmark_pipeline.evaluation.runner import EvaluationRunConfig, discover_test_suites, run_evaluation
from benchmark_pipeline.models import MavenResult


def passed_maven() -> MavenResult:
    return MavenResult(
        label="repo",
        exit_code=0,
        status="passed",
        status_reason=None,
        tests=0,
        failures=0,
        errors=0,
        skipped=0,
        failing_tests=[],
        stdout="",
        stderr="",
    )


class TestEvaluationRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("artifacts/.unit-tests/evaluation-runner")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_discover_test_suites_returns_single_suite(self) -> None:
        tests_dir = self.root / "tests"
        (tests_dir / "src/test/java").mkdir(parents=True)

        self.assertEqual(discover_test_suites(tests_dir), [tests_dir])

    def test_discover_test_suites_returns_sorted_benchmark_suites(self) -> None:
        benchmarks = self.root / "benchmarks"
        (benchmarks / "model-b/src/test/java").mkdir(parents=True)
        (benchmarks / "model-a/src/test/java").mkdir(parents=True)
        (benchmarks / "not-a-suite").mkdir(parents=True)

        self.assertEqual(
            discover_test_suites(benchmarks),
            [benchmarks / "model-a", benchmarks / "model-b"],
        )

    def test_run_evaluation_uses_model_specific_report_paths_for_multiple_suites(self) -> None:
        baseline_repo = self.root / "repo"
        benchmarks = self.root / "benchmarks"
        baseline_repo.mkdir()
        (benchmarks / "model-a/src/test/java").mkdir(parents=True)
        (benchmarks / "model-b/src/test/java").mkdir(parents=True)
        config = EvaluationRunConfig(
            baseline_repo=baseline_repo,
            tests_dir=benchmarks,
            report_json=self.root / "reports/evaluation_report.json",
            report_md=self.root / "reports/evaluation_report.md",
            pitest_report_dir=self.root / "reports/pit-reports",
            maven_cmd=["mvn", "test"],
        )

        with (
            patch("benchmark_pipeline.evaluation.runner.evaluate_repositories") as evaluate_repositories,
            redirect_stdout(StringIO()),
        ):
            evaluate_repositories.return_value = EvaluationOutcome(
                baseline_result=passed_maven(),
                baseline_coverage=None,
                pitest_result=None,
                disabled_tests=[],
            )
            runs = run_evaluation(config)

        self.assertEqual([run.suite_name for run in runs], ["model-a", "model-b"])
        self.assertEqual(runs[0].report_json, self.root / "reports/model-a_report.json")
        self.assertEqual(runs[1].report_md, self.root / "reports/model-b_report.md")
        self.assertEqual(evaluate_repositories.call_count, 2)


if __name__ == "__main__":
    unittest.main()
