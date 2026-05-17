from __future__ import annotations

from pathlib import Path
import shutil
import unittest

from benchmark_pipeline.report_summary import (
    find_comparison_reports,
    format_summary_markdown,
    summarize_report_payloads,
    write_summary_files,
)


class ReportSummaryTests(unittest.TestCase):
    def test_summarize_report_payloads_aggregates_model_metrics(self) -> None:
        payloads = [
            {
                "_report_path": "artifacts/runs/group/run-001/reports/comparison_report.json",
                "benchmark_profile": {"profile_id": "library", "domain": "library"},
                "rows": [
                    {
                        "test_model": "deepseek-v4-flash",
                        "generation_status": "passed",
                        "repair_outcome": "repair_successful",
                        "repair_attempts": 1,
                        "disabling_outcome": "disabling_not_needed",
                        "evaluation_status": "passed",
                        "tests": 10,
                        "failures": 0,
                        "errors": 0,
                        "skipped": 0,
                        "disabled_tests": 0,
                        "line_coverage": 0.8,
                        "branch_coverage": 0.7,
                        "instruction_coverage": 0.75,
                        "total_mutations": 100,
                        "killed": 80,
                        "survived": 10,
                        "no_coverage": 10,
                        "mutation_score": 0.8,
                        "before_repair": {
                            "after_tests": 10,
                            "after_failures": 1,
                            "after_errors": 0,
                            "after_skipped": 1,
                            "disabled_tests": 1,
                            "line_coverage": 0.75,
                            "branch_coverage": 0.65,
                            "instruction_coverage": 0.7,
                            "total_mutations": 100,
                            "killed": 75,
                            "survived": 15,
                            "no_coverage": 10,
                            "mutation_score": 0.75,
                        },
                        "after_repair": {
                            "after_tests": 10,
                            "after_failures": 0,
                            "after_errors": 0,
                            "after_skipped": 0,
                            "disabled_tests": 0,
                            "line_coverage": 0.8,
                            "branch_coverage": 0.7,
                            "instruction_coverage": 0.75,
                            "total_mutations": 100,
                            "killed": 80,
                            "survived": 10,
                            "no_coverage": 10,
                            "mutation_score": 0.8,
                        },
                    },
                    {
                        "test_model": "gpt-5-mini",
                        "generation_status": "failed",
                        "error": "Invalid JSON",
                    },
                ],
            },
            {
                "_report_path": "artifacts/runs/group/run-002/reports/comparison_report.json",
                "benchmark_profile": {"profile_id": "library", "domain": "library"},
                "rows": [
                    {
                        "test_model": "deepseek-v4-flash",
                        "generation_status": "passed",
                        "repair_outcome": "repair_not_needed",
                        "repair_attempts": 0,
                        "disabling_outcome": "disabling_not_needed",
                        "evaluation_status": "passed",
                        "tests": 20,
                        "failures": 0,
                        "errors": 0,
                        "skipped": 0,
                        "disabled_tests": 0,
                        "line_coverage": 0.9,
                        "branch_coverage": 0.8,
                        "instruction_coverage": 0.85,
                        "total_mutations": 120,
                        "killed": 90,
                        "survived": 20,
                        "no_coverage": 10,
                        "mutation_score": 0.75,
                        "before_repair": {
                            "after_tests": 20,
                            "after_failures": 0,
                            "after_errors": 0,
                            "after_skipped": 0,
                            "disabled_tests": 0,
                            "line_coverage": 0.9,
                            "branch_coverage": 0.8,
                            "instruction_coverage": 0.85,
                            "total_mutations": 120,
                            "killed": 90,
                            "survived": 20,
                            "no_coverage": 10,
                            "mutation_score": 0.75,
                        },
                        "after_repair": {
                            "after_tests": 20,
                            "after_failures": 0,
                            "after_errors": 0,
                            "after_skipped": 0,
                            "disabled_tests": 0,
                            "line_coverage": 0.9,
                            "branch_coverage": 0.8,
                            "instruction_coverage": 0.85,
                            "total_mutations": 120,
                            "killed": 90,
                            "survived": 20,
                            "no_coverage": 10,
                            "mutation_score": 0.75,
                        },
                    }
                ],
            },
        ]

        summary = summarize_report_payloads(payloads)
        deepseek = summary["models"]["deepseek-v4-flash"]
        failed = summary["models"]["gpt-5-mini"]

        self.assertEqual(summary["report_count"], 2)
        self.assertAlmostEqual(deepseek["generation_pass_rate"], 1.0)
        self.assertAlmostEqual(deepseek["final_pass_rate"], 1.0)
        self.assertAlmostEqual(deepseek["mean_repair_attempts"], 0.5)
        self.assertAlmostEqual(deepseek["final_means"]["tests"], 15.0)
        self.assertAlmostEqual(deepseek["final_means"]["line_coverage"], 0.85)
        self.assertAlmostEqual(deepseek["final_means"]["mutation_score"], 0.775)
        self.assertAlmostEqual(deepseek["repair_delta_means"]["mutation_score"], 0.025)
        self.assertEqual(failed["generation_status_counts"]["failed"], 1)
        self.assertIsNone(failed["final_pass_rate"])

    def test_find_and_write_summary_files(self) -> None:
        root = Path("tests") / "__tmp_report_summary"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True)
        try:
            report_path = root / "group" / "run-001" / "reports" / "comparison_report.json"
            report_path.parent.mkdir(parents=True)
            report_path.write_text('{"benchmark_profile":{"profile_id":"library","domain":"library"},"rows":[]}', encoding="utf-8")

            found = find_comparison_reports(root)
            self.assertEqual(found, [report_path])

            summary = {"report_count": 1, "models": {}, "profiles": {}}
            json_out = root / "summary.json"
            md_out = root / "summary.md"
            write_summary_files(summary, output_json=json_out, output_md=md_out)

            self.assertTrue(json_out.exists())
            self.assertTrue(md_out.exists())
            self.assertIn("# Comparison Report Summary", format_summary_markdown(summary))
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
