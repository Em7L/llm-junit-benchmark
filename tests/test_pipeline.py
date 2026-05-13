from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import _path  # noqa: F401

from benchmark_pipeline.evaluation.runner import EvaluationSuiteRun
from benchmark_pipeline.models import GeneratedRepo, GeneratedTests, MavenResult
from benchmark_pipeline.pipeline import PipelineConfig, run_pipeline


def generated_repo() -> GeneratedRepo:
    return GeneratedRepo(project_name="demo", description="demo", files=[])


def generated_tests() -> GeneratedTests:
    return GeneratedTests(summary="tests", files=[])


def evaluation_outcome_mock() -> Mock:
    return Mock(
        baseline_result=MavenResult(
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
    )


class TestPipeline(unittest.TestCase):
    def test_run_pipeline_composes_step_runners(self) -> None:
        config = PipelineConfig(
            repo_model="repo-model",
            tests_model="tests-model",
            project_name="demo-project",
            baseline_repo=Path("artifacts/baseline_repo"),
            tests_dir=Path("artifacts/generated_tests"),
            baseline_manifest=Path("artifacts/manifests/baseline_repo.json"),
            tests_manifest=Path("artifacts/manifests/generated_tests.json"),
            report_json=Path("artifacts/reports/evaluation_report.json"),
            report_md=Path("artifacts/reports/evaluation_report.md"),
            pitest_report_dir=Path("artifacts/reports/pit-reports"),
            maven_cmd=["mvn", "test"],
            max_repairs=2,
        )
        evaluation = evaluation_outcome_mock()

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()) as run_baseline_generation,
            patch("benchmark_pipeline.pipeline.run_test_generation", return_value=generated_tests()) as run_test_generation,
            patch(
                "benchmark_pipeline.pipeline.run_evaluation",
                return_value=[
                    EvaluationSuiteRun(
                        suite_name="evaluation",
                        suite_dir=config.tests_dir,
                        report_json=config.report_json,
                        report_md=config.report_md,
                        pitest_report_dir=config.pitest_report_dir,
                        outcome=evaluation,
                    )
                ],
            ) as run_evaluation,
            redirect_stdout(StringIO()),
        ):
            outcome = run_pipeline(config)

        baseline_config = run_baseline_generation.call_args.args[0]
        self.assertEqual(baseline_config.model, "repo-model")
        self.assertEqual(baseline_config.max_repairs, 2)
        self.assertEqual(baseline_config.manifest_path, config.baseline_manifest)

        tests_config = run_test_generation.call_args.args[0]
        self.assertEqual(tests_config.model, "tests-model")
        self.assertEqual(tests_config.max_repairs, 2)
        self.assertEqual(tests_config.manifest_path, config.tests_manifest)

        evaluation_config = run_evaluation.call_args.args[0]
        self.assertEqual(evaluation_config.baseline_repo, config.baseline_repo)
        self.assertEqual(evaluation_config.tests_dir, config.tests_dir)
        self.assertEqual(evaluation_config.report_json, config.report_json)

        self.assertIs(outcome.evaluation, evaluation)


if __name__ == "__main__":
    unittest.main()
