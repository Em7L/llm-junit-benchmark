from __future__ import annotations

import unittest
import shutil
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from benchmark_pipeline.evaluation import EvaluationOutcome
from benchmark_pipeline.evaluation.runner import EvaluationSuiteRun
from benchmark_pipeline.generation.profiles import get_benchmark_profile
from benchmark_pipeline.models import GeneratedRepo, GeneratedTests, MavenResult, PitestMutation, PitestResult
from benchmark_pipeline.pipeline import PipelineConfig, run_pipeline, safe_model_name, test_manifest_path


def generated_repo() -> GeneratedRepo:
    return GeneratedRepo(project_name="demo", description="demo", files=[])


def generated_tests() -> GeneratedTests:
    return GeneratedTests(summary="tests", files=[], repair_outcome="repair_not_needed", repair_attempts=0)


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


def evaluation_outcome(
    pitest_result: PitestResult | None = None,
    *,
    baseline_result: MavenResult | None = None,
    initial_baseline_result: MavenResult | None = None,
    disabled_tests: list[str] | None = None,
) -> EvaluationOutcome:
    return EvaluationOutcome(
        baseline_result=baseline_result or passed_maven(),
        baseline_coverage=None,
        pitest_result=pitest_result,
        disabled_tests=disabled_tests or [],
        initial_baseline_result=initial_baseline_result,
    )


def pitest_result(mutant_ids: list[str]) -> PitestResult:
    return PitestResult(
        exit_code=0,
        report_file="mutations.xml",
        total_mutations=len(mutant_ids),
        status_counts={"KILLED": len(mutant_ids)},
        mutation_score=1.0 if mutant_ids else None,
        mutations=[pitest_mutation(mutant_id) for mutant_id in mutant_ids],
        stdout="",
        stderr="",
    )


def pitest_mutation(mutant_id: str) -> PitestMutation:
    return PitestMutation(
        mutant_id=mutant_id,
        detected=True,
        status="KILLED",
        number_of_tests_run=1,
        source_file="App.java",
        mutated_class="com.example.App",
        mutated_method="run",
        method_description="()V",
        line_number=1,
        mutator="mutator",
        index=None,
        block=None,
        killing_test="AppTest",
        description="test mutant",
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
            benchmark_profile=get_benchmark_profile("low"),
            project_name="demo-project",
            baseline_repo=self.root / "baseline_repo",
            tests_dir=self.root / "generated_tests",
            profile_manifest=self.root / "manifests/benchmark_profile.json",
            baseline_manifest=self.root / "manifests/baseline_repo.json",
            tests_manifest=self.root / "manifests/generated_tests.json",
            report_json=self.root / "reports/comparison_report.json",
            report_md=self.root / "reports/comparison_report.md",
            pitest_report_dir=self.root / "reports/pit-reports",
            maven_cmd=["mvn", "test"],
            max_repairs=2,
        )

    def test_run_pipeline_composes_step_runners(self) -> None:
        config = self.config(("tests-model",))
        evaluation = evaluation_outcome()

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()) as run_baseline_generation,
            patch("benchmark_pipeline.pipeline.run_test_generation", return_value=generated_tests()) as run_test_generation,
            patch(
                "benchmark_pipeline.pipeline.run_evaluation",
                return_value=[
                    EvaluationSuiteRun(
                        suite_name="evaluation",
                        suite_dir=config.tests_dir,
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
        self.assertEqual(baseline_config.benchmark_profile.profile_id, "low")

        tests_config = run_test_generation.call_args.args[0]
        self.assertEqual(tests_config.model, "tests-model")
        self.assertEqual(tests_config.max_repairs, 2)
        self.assertEqual(tests_config.manifest_path, config.tests_manifest)
        self.assertEqual(tests_config.output_dir, config.tests_dir / "_final_selected" / "tests-model")

        evaluation_config = run_evaluation.call_args.args[0]
        self.assertEqual(evaluation_config.baseline_repo, config.baseline_repo)
        self.assertEqual(evaluation_config.tests_dir, config.tests_dir / "_final_selected")

        self.assertIs(outcome.evaluation, evaluation)
        profile_manifest = json.loads(config.profile_manifest.read_text(encoding="utf-8"))
        self.assertEqual(profile_manifest["profile_id"], "low")

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
        self.assertEqual(first_config.output_dir, config.tests_dir / "_final_selected" / "model-b")
        self.assertEqual(first_config.manifest_path, self.root / "manifests/generated_tests_model-b.json")
        self.assertEqual(second_config.model, "model-c")
        self.assertEqual(second_config.output_dir, config.tests_dir / "_final_selected" / "model-c")
        self.assertEqual(second_config.manifest_path, self.root / "manifests/generated_tests_model-c.json")

    def test_run_pipeline_removes_staging_root_at_end(self) -> None:
        config = self.config(("model-b",))

        def create_staging_dir(_generation_config) -> GeneratedTests:
            staging_root = config.baseline_repo.parent / ".staging"
            staging_root.mkdir(parents=True, exist_ok=True)
            (staging_root / "placeholder").mkdir(parents=True, exist_ok=True)
            return generated_tests()

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch("benchmark_pipeline.pipeline.run_test_generation", side_effect=create_staging_dir),
            patch("benchmark_pipeline.pipeline.run_evaluation", return_value=[]),
            redirect_stdout(StringIO()),
        ):
            run_pipeline(config)

        self.assertFalse((config.baseline_repo.parent / ".staging").exists())

    def test_run_pipeline_removes_target_dirs_from_preserved_artifacts(self) -> None:
        config = self.config(("model-b",))

        def create_targets(_generation_config) -> GeneratedTests:
            (config.baseline_repo / "target" / "maven-status").mkdir(parents=True, exist_ok=True)
            (config.baseline_repo / "target" / "maven-status" / "inputFiles.lst").write_text(
                r"C:\tmp\absolute.java",
                encoding="utf-8",
            )
            target_dir = config.tests_dir / "_final_selected" / "model-b" / "target" / "surefire-reports"
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "TEST-demo.xml").write_text("<testsuite />", encoding="utf-8")
            return generated_tests()

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch("benchmark_pipeline.pipeline.run_test_generation", side_effect=create_targets),
            patch("benchmark_pipeline.pipeline.run_evaluation", return_value=[]),
            redirect_stdout(StringIO()),
        ):
            run_pipeline(config)

        self.assertFalse((config.baseline_repo / "target").exists())
        self.assertFalse((config.tests_dir / "_final_selected" / "model-b" / "target").exists())

    def test_run_pipeline_continues_when_one_test_model_fails(self) -> None:
        config = self.config(("model-b", "model-c", "model-d"))

        def generate_or_fail(generation_config) -> GeneratedTests:
            model = generation_config.model
            if model == "model-c":
                generation_config.output_dir.mkdir(parents=True)
                (generation_config.output_dir / "partial.txt").write_text("partial output", encoding="utf-8")
                raise RuntimeError("model-c failed")
            return generated_tests()

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch("benchmark_pipeline.pipeline.run_test_generation", side_effect=generate_or_fail) as run_test_generation,
            patch("benchmark_pipeline.pipeline.run_evaluation", return_value=[]) as run_evaluation,
            redirect_stdout(StringIO()),
        ):
            outcome = run_pipeline(config)

        self.assertEqual(run_test_generation.call_count, 3)
        self.assertEqual(sorted(outcome.generated_tests), ["model-b", "model-d"])
        self.assertEqual(outcome.test_generation_errors, {"model-c": "model-c failed"})
        self.assertFalse((config.tests_dir / "_final_selected" / "model-c").exists())
        self.assertFalse((config.tests_dir / "_initial_snapshot" / "model-c").exists())
        run_evaluation.assert_called_once()
        comparison = json.loads((config.report_json.parent / "comparison_report.json").read_text(encoding="utf-8"))
        self.assertEqual([row["test_model"] for row in comparison["rows"]], ["model-b", "model-c", "model-d"])
        self.assertEqual(comparison["benchmark_profile"]["profile_id"], "low")
        self.assertEqual(comparison["rows"][1]["generation_status"], "failed")
        self.assertTrue((config.report_md.parent / "comparison_report.md").exists())

    def test_comparison_report_marks_identical_mutant_sets(self) -> None:
        config = self.config(("model-b", "model-c"))
        model_b_outcome = evaluation_outcome(pitest_result(["mutant-1", "mutant-2"]))
        model_c_outcome = evaluation_outcome(pitest_result(["mutant-1", "mutant-2"]))

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch("benchmark_pipeline.pipeline.run_test_generation", side_effect=[generated_tests(), generated_tests()]),
            patch(
                "benchmark_pipeline.pipeline.run_evaluation",
                return_value=[
                        EvaluationSuiteRun(
                            suite_name="model-b",
                            suite_dir=config.tests_dir / "_final_selected" / "model-b",
                            pitest_report_dir=config.pitest_report_dir / "_final_selected" / "model-b",
                            outcome=model_b_outcome,
                        ),
                        EvaluationSuiteRun(
                            suite_name="model-c",
                            suite_dir=config.tests_dir / "_final_selected" / "model-c",
                            pitest_report_dir=config.pitest_report_dir / "_final_selected" / "model-c",
                            outcome=model_c_outcome,
                        ),
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            run_pipeline(config)

        comparison = json.loads((config.report_json.parent / "comparison_report.json").read_text(encoding="utf-8"))
        self.assertEqual(
            comparison["mutant_set"],
            {
                "comparable_suite_count": 2,
                "identical": True,
                "common_mutants": 2,
                "union_mutants": 2,
                "per_suite_mutants": {
                    "_final_selected/model-b": 2,
                    "_final_selected/model-c": 2,
                },
                "only_in_suite": {
                    "_final_selected/model-b": [],
                    "_final_selected/model-c": [],
                },
            },
        )
        comparison_markdown = (config.report_md.parent / "comparison_report.md").read_text(encoding="utf-8")
        self.assertIn("Benchmark profile: `low`", comparison_markdown)
        self.assertIn("Identical mutant IDs across suites: `True`", comparison_markdown)

    def test_comparison_report_includes_final_suite_status_and_cleaning_outcome(self) -> None:
        config = self.config(("model-b",))
        initial = MavenResult(
            label="repo",
            exit_code=1,
            status="test_failures",
            status_reason="One or more tests failed.",
            tests=3,
            failures=1,
            errors=0,
            skipped=0,
            failing_tests=["com.example.AppTest#failsOnBaseline"],
            stdout="",
            stderr="",
        )
        final = MavenResult(
            label="repo",
            exit_code=0,
            status="passed",
            status_reason=None,
            tests=3,
            failures=0,
            errors=0,
            skipped=1,
            failing_tests=[],
            stdout="",
            stderr="",
        )
        outcome = evaluation_outcome(
            pitest_result(["mutant-1"]),
            baseline_result=final,
            initial_baseline_result=initial,
            disabled_tests=["com.example.AppTest#failsOnBaseline"],
        )

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch("benchmark_pipeline.pipeline.run_test_generation", return_value=generated_tests()),
            patch(
                "benchmark_pipeline.pipeline.run_evaluation",
                return_value=[
                        EvaluationSuiteRun(
                            suite_name="model-b",
                            suite_dir=config.tests_dir / "_final_selected" / "model-b",
                            pitest_report_dir=config.pitest_report_dir / "_final_selected" / "model-b",
                            outcome=outcome,
                        )
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            run_pipeline(config)

        comparison = json.loads((config.report_json.parent / "comparison_report.json").read_text(encoding="utf-8"))
        row = comparison["rows"][0]
        self.assertEqual(row["repair_outcome"], "repair_not_needed")
        self.assertEqual(row["repair_attempts"], 0)
        self.assertEqual(row["final_suite_before_disabling_status"], "test_failures")
        self.assertEqual(row["final_suite_disabling_outcome"], "disabling_applied_successful")
        self.assertEqual(row["disabling_outcome"], "disabling_applied_successful")
        self.assertEqual(row["initial_generated_suite"]["before_failures"], 1)
        self.assertEqual(row["initial_generated_suite"]["after_failures"], 0)
        self.assertEqual(row["initial_generated_suite"]["after_skipped"], 1)

    def test_run_pipeline_records_before_repair_evaluation_when_repairs_were_attempted(self) -> None:
        config = self.config(("model-b",))
        repaired_tests = GeneratedTests(
            summary="tests",
            files=[],
            repair_outcome="repair_successful",
            repair_attempts=1,
            repair_reasons=["verification_failure"],
        )
        before_outcome = evaluation_outcome(
            pitest_result(["mutant-1"]),
            baseline_result=MavenResult(
                label="repo",
                exit_code=0,
                status="passed",
                status_reason=None,
                tests=2,
                failures=0,
                errors=0,
                skipped=1,
                failing_tests=[],
                stdout="",
                stderr="",
            ),
            initial_baseline_result=MavenResult(
                label="repo",
                exit_code=1,
                status="test_failures",
                status_reason="One or more tests failed.",
                tests=2,
                failures=1,
                errors=0,
                skipped=0,
                failing_tests=["com.example.AppTest#failsOnBaseline"],
                stdout="",
                stderr="",
            ),
            disabled_tests=["com.example.AppTest#failsOnBaseline"],
        )

        def generate_with_initial_dir(generation_config) -> GeneratedTests:
            assert generation_config.initial_output_dir is not None
            generation_config.initial_output_dir.mkdir(parents=True, exist_ok=True)
            return repaired_tests

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch("benchmark_pipeline.pipeline.run_test_generation", side_effect=generate_with_initial_dir),
            patch(
                "benchmark_pipeline.pipeline.run_evaluation",
                side_effect=[
                    [
                        EvaluationSuiteRun(
                            suite_name="model-b",
                            suite_dir=config.tests_dir / "_final_selected" / "model-b",
                            pitest_report_dir=config.pitest_report_dir / "_final_selected" / "model-b",
                            outcome=evaluation_outcome(pitest_result(["mutant-1"])),
                        )
                    ],
                    [
                        EvaluationSuiteRun(
                            suite_name="model-b",
                            suite_dir=config.tests_dir / "_initial_snapshot" / "model-b",
                            pitest_report_dir=config.pitest_report_dir / "_initial_snapshot" / "model-b",
                            outcome=before_outcome,
                        )
                    ],
                ],
            ) as run_evaluation,
            redirect_stdout(StringIO()),
        ):
            run_pipeline(config)

        self.assertEqual(run_evaluation.call_args_list[1].args[0].tests_dir, config.tests_dir / "_initial_snapshot" / "model-b")
        self.assertEqual(run_evaluation.call_args_list[1].args[0].pitest_report_dir, config.pitest_report_dir / "_initial_snapshot" / "model-b")
        comparison = json.loads((config.report_json.parent / "comparison_report.json").read_text(encoding="utf-8"))
        row = comparison["rows"][0]
        self.assertEqual(row["initial_generated_suite"]["before_disabling_status"], "test_failures")
        self.assertEqual(row["initial_generated_suite"]["before_failures"], 1)
        self.assertEqual(row["initial_generated_suite"]["disabling_outcome"], "disabling_applied_successful")
        self.assertEqual(row["final_generated_suite"]["after_disabling_status"], "passed")
        self.assertEqual(comparison["mutant_set"]["comparable_suite_count"], 2)
        self.assertEqual(
            comparison["mutant_set"]["per_suite_mutants"],
            {
                "_initial_snapshot/model-b": 1,
                "_final_selected/model-b": 1,
            },
        )
        comparison_markdown = (config.report_md.parent / "comparison_report.md").read_text(encoding="utf-8")
        self.assertIn("## Generation And Repair Summary", comparison_markdown)
        self.assertIn("## Initial Generated Suite", comparison_markdown)
        self.assertIn("## Final Selected Suite", comparison_markdown)
        self.assertIn("| Test model | Generation | Repair | Repair tries |", comparison_markdown)
        self.assertIn(
            "| Test model | Status | Tests | Test Failures | Test Errors | Skipped tests |",
            comparison_markdown,
        )
        self.assertIn("`generation=passed`", comparison_markdown)
        self.assertIn("`maven_status=test_failures`", comparison_markdown)
        self.assertIn("`maven_status=passed`", comparison_markdown)

    def test_run_pipeline_reuses_final_evaluation_when_initial_and_final_suites_match(self) -> None:
        config = self.config(("model-b",))
        repaired_tests = GeneratedTests(
            summary="tests",
            files=[],
            repair_outcome="repair_discarded_incomplete",
            repair_attempts=1,
            repair_reasons=["verification_failure"],
        )
        shared_outcome = evaluation_outcome(pitest_result(["mutant-1"]))

        def generate_with_matching_dirs(generation_config) -> GeneratedTests:
            assert generation_config.initial_output_dir is not None
            generation_config.output_dir.mkdir(parents=True, exist_ok=True)
            generation_config.initial_output_dir.mkdir(parents=True, exist_ok=True)
            content = "class AppTest {}"
            relative = Path("src/test/java/com/example/AppTest.java")
            for root in (generation_config.output_dir, generation_config.initial_output_dir):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            return repaired_tests

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch("benchmark_pipeline.pipeline.run_test_generation", side_effect=generate_with_matching_dirs),
            patch(
                "benchmark_pipeline.pipeline.run_evaluation",
                return_value=[
                        EvaluationSuiteRun(
                            suite_name="model-b",
                            suite_dir=config.tests_dir / "_final_selected" / "model-b",
                            pitest_report_dir=config.pitest_report_dir / "_final_selected" / "model-b",
                            outcome=shared_outcome,
                        )
                ],
            ) as run_evaluation,
            redirect_stdout(StringIO()),
        ):
            run_pipeline(config)

        run_evaluation.assert_called_once()
        comparison = json.loads((config.report_json.parent / "comparison_report.json").read_text(encoding="utf-8"))
        row = comparison["rows"][0]
        self.assertEqual(row["initial_generated_suite"], row["final_generated_suite"])
        self.assertEqual(comparison["mutant_set"]["comparable_suite_count"], 1)

    def test_comparison_report_marks_different_mutant_sets(self) -> None:
        config = self.config(("model-b", "model-c"))
        model_b_outcome = evaluation_outcome(pitest_result(["mutant-1", "mutant-2"]))
        model_c_outcome = evaluation_outcome(pitest_result(["mutant-1", "mutant-3"]))

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch("benchmark_pipeline.pipeline.run_test_generation", side_effect=[generated_tests(), generated_tests()]),
            patch(
                "benchmark_pipeline.pipeline.run_evaluation",
                return_value=[
                        EvaluationSuiteRun(
                            suite_name="model-b",
                            suite_dir=config.tests_dir / "_final_selected" / "model-b",
                            pitest_report_dir=config.pitest_report_dir / "_final_selected" / "model-b",
                            outcome=model_b_outcome,
                        ),
                        EvaluationSuiteRun(
                            suite_name="model-c",
                            suite_dir=config.tests_dir / "_final_selected" / "model-c",
                            pitest_report_dir=config.pitest_report_dir / "_final_selected" / "model-c",
                            outcome=model_c_outcome,
                        ),
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            run_pipeline(config)

        comparison = json.loads((config.report_json.parent / "comparison_report.json").read_text(encoding="utf-8"))
        self.assertFalse(comparison["mutant_set"]["identical"])
        self.assertEqual(comparison["mutant_set"]["common_mutants"], 1)
        self.assertEqual(comparison["mutant_set"]["union_mutants"], 3)
        self.assertEqual(comparison["mutant_set"]["only_in_suite"]["_final_selected/model-b"], ["mutant-2"])
        self.assertEqual(comparison["mutant_set"]["only_in_suite"]["_final_selected/model-c"], ["mutant-3"])

    def test_compile_failed_snapshot_uses_na_for_execution_counts(self) -> None:
        config = self.config(("model-b",))
        compile_failed = MavenResult(
            label="repo",
            exit_code=1,
            status="test_compile_failure",
            status_reason="Test sources did not compile.",
            tests=0,
            failures=0,
            errors=0,
            skipped=0,
            failing_tests=[],
            stdout="",
            stderr="",
        )

        with (
            patch("benchmark_pipeline.pipeline.run_baseline_generation", return_value=generated_repo()),
            patch(
                "benchmark_pipeline.pipeline.run_test_generation",
                return_value=GeneratedTests(summary="tests", files=[], repair_outcome="repair_not_needed", repair_attempts=0),
            ),
            patch(
                "benchmark_pipeline.pipeline.run_evaluation",
                return_value=[
                    EvaluationSuiteRun(
                        suite_name="model-b",
                        suite_dir=config.tests_dir / "_final_selected" / "model-b",
                        pitest_report_dir=config.pitest_report_dir / "_final_selected" / "model-b",
                        outcome=evaluation_outcome(baseline_result=compile_failed),
                    )
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            run_pipeline(config)

        comparison = json.loads((config.report_json.parent / "comparison_report.json").read_text(encoding="utf-8"))
        row = comparison["rows"][0]
        self.assertIsNone(row["final_generated_suite"]["before_tests"])
        self.assertIsNone(row["final_generated_suite"]["before_failures"])
        self.assertIsNone(row["final_generated_suite"]["before_errors"])
        self.assertIsNone(row["final_generated_suite"]["after_tests"])
        comparison_markdown = (config.report_md.parent / "comparison_report.md").read_text(encoding="utf-8")
        self.assertIn("| model-b | test_compile_failure | N/A | N/A | N/A |", comparison_markdown)

    def test_run_pipeline_writes_comparison_report_when_all_test_models_fail(self) -> None:
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
            outcome = run_pipeline(config)

        run_evaluation.assert_not_called()
        self.assertEqual(outcome.generated_tests, {})
        self.assertEqual(
            outcome.test_generation_errors,
            {"model-b": "model-b failed", "model-c": "model-c failed"},
        )
        comparison = json.loads((config.report_json.parent / "comparison_report.json").read_text(encoding="utf-8"))
        self.assertEqual([row["generation_status"] for row in comparison["rows"]], ["failed", "failed"])

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
