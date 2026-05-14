from __future__ import annotations

import unittest

import _path  # noqa: F401

from benchmark_pipeline.classifications import classify_disabling as disabling_outcome
from benchmark_pipeline.models import GeneratedTests, MavenResult
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
    def test_markdown_report_includes_initial_cleaning_and_final_sections(self) -> None:
        report = markdown_report(
            baseline_result=maven_result("passed"),
            baseline_coverage=None,
            pitest_result=None,
            disabled_tests=["com.example.AppTest#failsOnBaseline"],
            initial_baseline_result=maven_result("test_failures", ["com.example.AppTest#failsOnBaseline"]),
            generated_tests=GeneratedTests(
                summary="tests",
                files=[],
                repair_attempts=1,
                repair_outcome="repair_successful",
                repair_reasons=["verification_failure"],
            ),
        )

        self.assertIn("## Test Generation Repair", report)
        self.assertIn("- Repair outcome: `repair_successful`", report)
        self.assertIn("## Initial Baseline Validation", report)
        self.assertIn("## Baseline-Failing Test Disabling", report)
        self.assertIn("- Disabling applied: `True`", report)
        self.assertIn("- Disabling outcome: `disabling_applied_successful`", report)
        self.assertIn("- Disabled generated test methods: `1`", report)
        self.assertIn("- `com.example.AppTest#failsOnBaseline`", report)
        self.assertIn("## Final Baseline Validation", report)
        self.assertIn("## Classification Definitions", report)
        self.assertIn("`repair_successful`", report)
        self.assertIn("`maven_status=test_failures`", report)
        self.assertIn("`maven_status=passed`", report)
        self.assertIn("`disabling_applied_successful`", report)
        self.assertNotIn("final baseline test suite did not pass", report)

    def test_disabling_outcome_reports_not_needed_without_initial_failure(self) -> None:
        result = maven_result("passed")
        self.assertEqual(disabling_outcome(baseline_result=result), "disabling_not_needed")

    def test_disabling_outcome_reports_no_effect_when_metrics_do_not_change(self) -> None:
        initial = maven_result("test_failures", ["com.example.AppTest#failsOnBaseline"])
        final = maven_result("test_failures", ["com.example.AppTest#failsOnBaseline"])
        self.assertEqual(
            disabling_outcome(
                baseline_result=final,
                disabled_tests=["com.example.AppTest#failsOnBaseline"],
                initial_baseline_result=initial,
            ),
            "disabling_applied_no_effect",
        )


if __name__ == "__main__":
    unittest.main()
