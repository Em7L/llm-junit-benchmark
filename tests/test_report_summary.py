from __future__ import annotations

import json
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
                "benchmark_profile": {"profile_id": "low", "complexity": "low"},
                "rows": [
                    {
                        "test_model": "deepseek-v4-flash",
                        "generation_status": "passed",
                        "repair_outcome": "repair_successful",
                        "repair_attempts": 1,
                        "final_suite_before_disabling_status": "passed",
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
                        "initial_generated_suite": {
                            "before_disabling_status": "test_failures",
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
                        "final_generated_suite": {
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
                "benchmark_profile": {"profile_id": "low", "complexity": "low"},
                "rows": [
                    {
                        "test_model": "deepseek-v4-flash",
                        "generation_status": "passed",
                        "repair_outcome": "repair_not_needed",
                        "repair_attempts": 0,
                        "final_suite_before_disabling_status": "passed",
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
                        "final_generated_suite": {
                            "before_disabling_status": "passed",
                            "before_tests": 20,
                            "before_failures": 0,
                            "before_errors": 0,
                            "before_skipped": 0,
                            "after_disabling_status": "passed",
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
        self.assertAlmostEqual(deepseek["accepted_suite_rate"], 1.0)
        self.assertAlmostEqual(deepseek["initial_test_compile_rate"], 1.0)
        self.assertAlmostEqual(deepseek["final_test_compile_rate"], 1.0)
        self.assertAlmostEqual(deepseek["final_pass_rate"], 1.0)
        self.assertAlmostEqual(deepseek["mean_repair_attempts"], 0.5)
        self.assertAlmostEqual(deepseek["final_means"]["tests"], 15.0)
        self.assertAlmostEqual(deepseek["final_means"]["line_coverage"], 0.85)
        self.assertAlmostEqual(deepseek["final_means"]["mutation_score"], 0.775)
        self.assertAlmostEqual(deepseek["repair_delta_means"]["mutation_score"], 0.05)
        self.assertEqual(deepseek["repair_delta_stats"]["mutation_score"]["n"], 1)
        self.assertEqual(failed["generation_status_counts"]["failed"], 1)
        self.assertIsNone(failed["final_pass_rate"])
        markdown = format_summary_markdown(summary)
        self.assertIn("## Overall Results", markdown)
        self.assertIn("## Overall Variability", markdown)
        self.assertIn("## Repair Effects (Repaired Runs Only)", markdown)
        self.assertIn("## Profile `low`", markdown)
        self.assertIn("Accepted suite rate` means the pipeline accepted a generated suite artifact", markdown)
        self.assertIn("Initial test compile rate", markdown)
        self.assertIn("Final test compile rate", markdown)
        self.assertIn("Repair needed", markdown)
        self.assertIn("Avg tests", markdown)
        self.assertIn("## Profile `low` Variability", markdown)
        self.assertNotIn("Overall Outcome Counts", markdown)
        self.assertNotIn("Overall Final Generated Suite Averages", markdown)

    def test_find_and_write_summary_files(self) -> None:
        root = Path("tests") / "__tmp_report_summary"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True)
        try:
            report_path = root / "group" / "run-001" / "reports" / "comparison_report.json"
            report_path.parent.mkdir(parents=True)
            report_path.write_text('{"benchmark_profile":{"profile_id":"low","complexity":"low"},"rows":[]}', encoding="utf-8")

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

    def test_summary_markdown_reflects_written_json_payload(self) -> None:
        root = Path("tests") / "__tmp_report_summary_consistency"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True)
        try:
            summary = {
                "report_count": 2,
                "report_paths": [
                    "artifacts/runs/group/run-001/reports/comparison_report.json",
                    "artifacts/runs/group/run-002/reports/comparison_report.json",
                ],
                "models": {
                    "deepseek-v4-flash": {
                        "run_count": 2,
                        "accepted_suite_rate": 1.0,
                        "initial_test_compile_rate": 0.5,
                        "final_test_compile_rate": 1.0,
                        "final_pass_rate": 1.0,
                        "repair_needed_rate": 0.5,
                        "repaired_run_count": 1,
                        "final_means": {
                            "tests": 12.0,
                            "line_coverage": 0.81,
                            "branch_coverage": 0.74,
                            "mutation_score": 0.77,
                        },
                        "repair_delta_means": {
                            "line_coverage": 0.10,
                            "branch_coverage": 0.05,
                            "mutation_score": 0.03,
                        },
                        "final_stats": {
                            "line_coverage": {"n": 2, "stdev": 0.02},
                            "branch_coverage": {"n": 2, "stdev": 0.01},
                            "mutation_score": {"n": 2, "stdev": 0.03},
                        },
                    }
                },
                "profiles": {
                    "low": {
                        "models": {
                            "deepseek-v4-flash": {
                                "run_count": 2,
                                "initial_test_compile_rate": 0.5,
                                "final_test_compile_rate": 1.0,
                                "final_pass_rate": 1.0,
                                "repair_needed_rate": 0.5,
                                "final_means": {
                                    "tests": 12.0,
                                    "line_coverage": 0.81,
                                    "branch_coverage": 0.74,
                                    "mutation_score": 0.77,
                                },
                                "final_stats": {
                                    "line_coverage": {"n": 2, "stdev": 0.02},
                                    "branch_coverage": {"n": 2, "stdev": 0.01},
                                    "mutation_score": {"n": 2, "stdev": 0.03},
                                },
                            }
                        }
                    }
                },
            }

            json_out = root / "summary.json"
            md_out = root / "summary.md"
            write_summary_files(summary, output_json=json_out, output_md=md_out)

            persisted_summary = json.loads(json_out.read_text(encoding="utf-8"))
            markdown = md_out.read_text(encoding="utf-8")

            self.assertEqual(persisted_summary["report_count"], 2)
            self.assertEqual(persisted_summary["models"]["deepseek-v4-flash"]["run_count"], 2)
            self.assertEqual(
                persisted_summary["models"]["deepseek-v4-flash"]["final_means"]["mutation_score"],
                0.77,
            )

            self.assertIn("- Reports aggregated: `2`", markdown)
            self.assertIn("## Overall Results", markdown)
            self.assertIn("| deepseek-v4-flash | 2 | 100.00% | 50.00% | 100.00% | 100.00% | 50.00% | 12.00 | 81.00% | 74.00% | 77.00% |", markdown)
            self.assertIn("## Overall Variability", markdown)
            self.assertIn("## Repair Effects (Repaired Runs Only)", markdown)
            self.assertIn("## Profile `low`", markdown)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
