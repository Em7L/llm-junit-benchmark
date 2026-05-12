from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from benchmark_pipeline.evaluation import evaluate_repositories
from benchmark_pipeline.models import MavenResult, PitestResult


def maven_result(status: str, failing_tests: list[str] | None = None) -> MavenResult:
    return MavenResult(
        label="repo",
        exit_code=0 if status == "passed" else 1,
        status=status,
        status_reason=None,
        tests=1,
        failures=len(failing_tests or []),
        errors=0,
        skipped=0,
        failing_tests=failing_tests or [],
        stdout="",
        stderr="",
    )


class TestEvaluation(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("artifacts/.unit-tests/evaluation")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.repo = self.root / "repo"
        self.tests = self.root / "tests"
        self._write_minimal_repo_and_tests()

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_disables_failing_tests_then_runs_pitest_on_cleaned_baseline(self) -> None:
        pitest_result = PitestResult(
            exit_code=0,
            report_file=None,
            total_mutations=0,
            status_counts={},
            mutation_score=None,
            mutations=[],
            stdout="",
            stderr="",
        )

        with (
            patch(
                "benchmark_pipeline.evaluation.run_maven_tests",
                side_effect=[
                    maven_result("test_failures", ["com.example.AppTest#failsOnBaseline"]),
                    maven_result("passed"),
                ],
            ) as run_maven_tests,
            patch("benchmark_pipeline.evaluation.run_pitest", return_value=pitest_result) as run_pitest,
            patch("benchmark_pipeline.evaluation.run_maven_command"),
        ):
            outcome = evaluate_repositories(
                baseline_repo=self.repo,
                tests_dir=self.tests,
                maven_cmd=["mvn", "test"],
            )

        self.assertEqual(run_maven_tests.call_count, 2)
        self.assertEqual(run_pitest.call_count, 1)
        self.assertTrue(outcome.baseline_result.passed)
        self.assertEqual(outcome.disabled_tests, ["com.example.AppTest#failsOnBaseline"])
        self.assertIsNotNone(outcome.initial_baseline_result)

    def test_skips_cleanup_and_pitest_when_tests_do_not_compile(self) -> None:
        with (
            patch(
                "benchmark_pipeline.evaluation.run_maven_tests",
                return_value=maven_result("test_compile_failure"),
            ) as run_maven_tests,
            patch("benchmark_pipeline.evaluation.run_pitest") as run_pitest,
            patch("benchmark_pipeline.evaluation.run_maven_command"),
        ):
            outcome = evaluate_repositories(
                baseline_repo=self.repo,
                tests_dir=self.tests,
                maven_cmd=["mvn", "test"],
            )

        self.assertEqual(run_maven_tests.call_count, 1)
        self.assertEqual(run_pitest.call_count, 0)
        self.assertEqual(outcome.disabled_tests, [])
        self.assertIsNone(outcome.pitest_result)

    def _write_minimal_repo_and_tests(self) -> None:
        (self.repo / "src/main/java/com/example").mkdir(parents=True)
        (self.tests / "src/test/java/com/example").mkdir(parents=True)
        (self.repo / "pom.xml").write_text("<project/>", encoding="utf-8")
        (self.repo / "src/main/java/com/example/App.java").write_text("class App {}", encoding="utf-8")
        (self.tests / "src/test/java/com/example/AppTest.java").write_text(
            "\n".join(
                [
                    "package com.example;",
                    "",
                    "import org.junit.jupiter.api.Test;",
                    "",
                    "class AppTest {",
                    "    @Test",
                    "    void failsOnBaseline() {",
                    "    }",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
