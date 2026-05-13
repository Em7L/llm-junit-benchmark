from __future__ import annotations

import shutil
import unittest
from pathlib import Path

import _path  # noqa: F401

from benchmark_pipeline.tools.maven import (
    classify_maven_result,
    parse_jacoco_report,
    parse_surefire_failing_tests,
    parse_surefire_reports,
)


class TestMavenParsing(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("artifacts/.unit-tests/maven")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_parse_surefire_totals_and_failing_tests(self) -> None:
        report_dir = self.root / "target/surefire-reports"
        report_dir.mkdir(parents=True)
        (report_dir / "TEST-com.example.AppTest.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.AppTest" tests="3" failures="1" errors="1" skipped="0">
  <testcase classname="com.example.AppTest" name="passes"/>
  <testcase classname="com.example.AppTest" name="fails"><failure>bad</failure></testcase>
  <testcase classname="com.example.AppTest" name="errors"><error>boom</error></testcase>
</testsuite>
""",
            encoding="utf-8",
        )

        self.assertEqual(parse_surefire_reports(report_dir), (3, 1, 1, 0))
        self.assertEqual(
            parse_surefire_failing_tests(report_dir),
            ["com.example.AppTest#errors", "com.example.AppTest#fails"],
        )

    def test_classifies_test_failures_before_generic_maven_failure(self) -> None:
        status, reason = classify_maven_result(
            exit_code=1,
            stdout="",
            stderr="",
            report_dir=self.root / "target/surefire-reports",
            failures=1,
            errors=0,
        )

        self.assertEqual(status, "test_failures")
        self.assertEqual(reason, "One or more tests failed.")

    def test_parse_jacoco_report_rates(self) -> None:
        report_file = self.root / "target/site/jacoco/jacoco.xml"
        report_file.parent.mkdir(parents=True)
        report_file.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<report name="sample">
  <counter type="INSTRUCTION" missed="2" covered="8"/>
  <counter type="LINE" missed="1" covered="3"/>
  <counter type="BRANCH" missed="2" covered="2"/>
</report>
""",
            encoding="utf-8",
        )

        coverage = parse_jacoco_report(report_file)

        self.assertIsNotNone(coverage)
        assert coverage is not None
        self.assertEqual(coverage.instructions_covered, 8)
        self.assertEqual(coverage.lines_missed, 1)
        self.assertEqual(coverage.instruction_rate, 0.8)
        self.assertEqual(coverage.line_rate, 0.75)
        self.assertEqual(coverage.branch_rate, 0.5)


if __name__ == "__main__":
    unittest.main()
