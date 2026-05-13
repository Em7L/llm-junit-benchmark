from __future__ import annotations

import unittest

import _path  # noqa: F401

from benchmark_pipeline.models import MavenResult
from benchmark_pipeline.evaluation.reports import markdown_report


def maven_result(status: str, failing_tests: list[str] | None = None) -> MavenResult:
    return MavenResult(
        label="repo",
        exit_code=0 if status == "passed" else 1,
        status=status,
        status_reason=None,
        tests=2,
        failures=len(failing_tests or []),
        errors=0,
        skipped=0,
        failing_tests=failing_tests or [],
        stdout="",
        stderr="",
    )


class TestReports(unittest.TestCase):
    def test_markdown_report_includes_baseline_cleaning_section(self) -> None:
        report = markdown_report(
            baseline_result=maven_result("passed"),
            baseline_coverage=None,
            pitest_result=None,
            disabled_tests=["com.example.AppTest#failsOnBaseline"],
            initial_baseline_result=maven_result("test_failures", ["com.example.AppTest#failsOnBaseline"]),
        )

        self.assertIn("## Baseline Test Cleaning", report)
        self.assertIn("- Initial run status: `test_failures`", report)
        self.assertIn("- Disabled generated test methods: `1`", report)
        self.assertIn("- `com.example.AppTest#failsOnBaseline`", report)
        self.assertIn("final baseline test suite did not pass", report)


if __name__ == "__main__":
    unittest.main()
