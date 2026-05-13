from __future__ import annotations

import unittest
import shutil
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import _path  # noqa: F401

from benchmark_pipeline.evaluation.runner import EvaluationSuiteRun
from benchmark_pipeline.models import GeneratedRepo, GeneratedTests, MavenResult
from benchmark_pipeline.pipeline import PipelineConfig, run_pipeline, safe_model_name, test_manifest_path


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
    def setUp(self) -> None:
        self.root = Path("artifacts/.unit-tests/pipeline")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def config(self, tests_models: tuple[str, ...]) -> PipelineConfig:
        return PipelineConfig(
            repo_model="repo-model",
            tests_models=tests_models,
            project_name="demo-project",
            baseline_repo=self.root / "baseline_repo",
            tests_dir=self.root / "generated_tests",
            baseline_manifest=self.root / "manifests/baseline_repo.json",
            tests_manifest=self.root / "manifests/generated_tests.json",
            report_json=self.root / "reports/evaluation_report.json",
            report_md=self.root / "reports/evaluation_report.md",
            pitest_report_dir=self.root / "reports/pit-reports",
            maven_cmd=["mvn", "test"],
            max_repairs=2,
        )

    def test_run_pipeline_composes_step_runners(self) -> None:
        config = self.config(("tests-model",))
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
        self.assertEqual(tests_config.output_dir, config.tests_dir / "tests-model")

        evaluation_config = run_evaluation.call_args.args[0]
        self.assertEqual(evaluation_config.baseline_repo, config.baseline_repo)
        self.assertEqual(evaluation_config.tests_dir, config.tests_dir)
        self.assertEqual(evaluation_config.report_json, config.report_json)

        self.assertIs(outcome.evaluation, evaluation)

    def test_run_pipeline_generates_one_suite_per_test_model(self) -> None:
        config = self.config(("model-b", "model-c"))

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch("benchmark_pipeline.pipeline.run_test_generation", side_effect=[generated_tests(), generated_tests()]) as run_test_generation,
            patch("benchmark_pipeline.pipeline.run_evaluation", return_value=[]),
            redirect_stdout(StringIO()),
        ):
            run_pipeline(config)

        first_config = run_test_generation.call_args_list[0].args[0]
        second_config = run_test_generation.call_args_list[1].args[0]
        self.assertEqual(first_config.model, "model-b")
        self.assertEqual(first_config.output_dir, config.tests_dir / "model-b")
        self.assertEqual(first_config.manifest_path, self.root / "manifests/generated_tests_model-b.json")
        self.assertEqual(second_config.model, "model-c")
        self.assertEqual(second_config.output_dir, config.tests_dir / "model-c")
        self.assertEqual(second_config.manifest_path, self.root / "manifests/generated_tests_model-c.json")

    def test_run_pipeline_continues_when_one_test_model_fails(self) -> None:
        config = self.config(("model-b", "model-c", "model-d"))

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch(
                "benchmark_pipeline.pipeline.run_test_generation",
                side_effect=[generated_tests(), RuntimeError("model-c failed"), generated_tests()],
            ) as run_test_generation,
            patch("benchmark_pipeline.pipeline.run_evaluation", return_value=[]) as run_evaluation,
            redirect_stdout(StringIO()),
        ):
            outcome = run_pipeline(config)

        self.assertEqual(run_test_generation.call_count, 3)
        self.assertEqual(sorted(outcome.generated_tests), ["model-b", "model-d"])
        self.assertEqual(outcome.test_generation_errors, {"model-c": "model-c failed"})
        run_evaluation.assert_called_once()
        comparison = json.loads((config.report_json.parent / "comparison_report.json").read_text(encoding="utf-8"))
        self.assertEqual([row["test_model"] for row in comparison["rows"]], ["model-b", "model-c", "model-d"])
        self.assertEqual(comparison["rows"][1]["generation_status"], "failed")
        self.assertTrue((config.report_md.parent / "comparison_report.md").exists())

    def test_run_pipeline_fails_when_all_test_models_fail(self) -> None:
        config = self.config(("model-b", "model-c"))

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch(
                "benchmark_pipeline.pipeline.run_test_generation",
                side_effect=[RuntimeError("model-b failed"), RuntimeError("model-c failed")],
            ),
            patch("benchmark_pipeline.pipeline.run_evaluation") as run_evaluation,
            redirect_stdout(StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "All test-generation models failed"):
                run_pipeline(config)

        run_evaluation.assert_not_called()

    def test_safe_model_name_removes_path_unsafe_characters(self) -> None:
        self.assertEqual(safe_model_name("provider/model:latest"), "provider_model_latest")

    def test_test_manifest_path_supports_directory_or_single_file_paths(self) -> None:
        self.assertEqual(
            test_manifest_path(Path("artifacts/manifests/generated_tests.json"), "model-a", is_multi_model=False),
            Path("artifacts/manifests/generated_tests.json"),
        )
        self.assertEqual(
            test_manifest_path(Path("artifacts/manifests/generated_tests.json"), "model-a", is_multi_model=True),
            Path("artifacts/manifests/generated_tests_model-a.json"),
        )
        self.assertEqual(
            test_manifest_path(Path("artifacts/manifests/generated_tests"), "model-a", is_multi_model=True),
            Path("artifacts/manifests/generated_tests/model-a_tests.json"),
        )


if __name__ == "__main__":
    unittest.main()
