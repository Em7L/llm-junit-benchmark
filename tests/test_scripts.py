from __future__ import annotations

import importlib.util
import shutil
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

import _path  # noqa: F401

from benchmark_pipeline.models import GeneratedRepo, GeneratedTests, MavenResult


def load_script(filename: str) -> ModuleType:
    script_path = Path(filename).resolve()
    module_name = filename.replace(".py", "").replace("_", "-") + "-test-module"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load script: {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo() -> GeneratedRepo:
    return GeneratedRepo(project_name="demo", description="demo", files=[])


def tests() -> GeneratedTests:
    return GeneratedTests(summary="demo", files=[])


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


class TestScripts(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("artifacts/.unit-tests/scripts")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_run_pipeline_script_builds_config_from_cli_args(self) -> None:
        module = load_script("0_run_pipeline.py")
        run_pipeline = Mock()
        argv = [
            "0_run_pipeline.py",
            "--model",
            "default-model",
            "--repo-model",
            "repo-model",
            "--tests-model",
            "tests-model",
            "--project-name",
            "demo-project",
            "--baseline-repo",
            str(self.root / "baseline"),
            "--tests-dir",
            str(self.root / "tests"),
            "--output-root",
            str(self.root / "runs"),
            "--maven-cmd",
            "mvn",
            "verify",
            "--max-repairs",
            "3",
        ]

        with (
            patch.object(module, "run_pipeline", run_pipeline),
            patch.object(sys, "argv", argv),
            redirect_stdout(StringIO()),
        ):
            module.main()

        config = run_pipeline.call_args.args[0]
        self.assertEqual(config.repo_model, "repo-model")
        self.assertEqual(config.tests_models, ("tests-model",))
        self.assertEqual(config.project_name, "demo-project")
        self.assertEqual(config.maven_cmd, ["mvn", "verify"])
        self.assertEqual(config.max_repairs, 3)

    def test_run_pipeline_script_uses_next_preserved_run_directory_by_default(self) -> None:
        module = load_script("0_run_pipeline.py")
        run_pipeline = Mock()
        output_root = self.root / "runs"
        existing_run = output_root / "repo-repo-model__tests-test-model" / "run-001"
        existing_run.mkdir(parents=True)

        with (
            patch.object(module, "run_pipeline", run_pipeline),
            patch.object(
                sys,
                "argv",
                [
                    "0_run_pipeline.py",
                    "--repo-model",
                    "repo-model",
                    "--tests-model",
                    "test-model",
                    "--output-root",
                    str(output_root),
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            module.main()

        config = run_pipeline.call_args.args[0]
        expected_run = output_root / "repo-repo-model__tests-test-model" / "run-002"
        self.assertEqual(config.baseline_repo, expected_run / "baseline_repo")
        self.assertEqual(config.tests_dir, expected_run / "generated_tests")
        self.assertEqual(config.report_md, expected_run / "reports/comparison_report.md")

    def test_run_pipeline_script_accepts_multiple_test_models(self) -> None:
        module = load_script("0_run_pipeline.py")
        run_pipeline = Mock()
        argv = [
            "0_run_pipeline.py",
            "--repo-model",
            "repo-model",
            "--tests-models",
            "model-b",
            "model-c",
            "model-d",
            "--output-root",
            str(self.root / "runs"),
        ]

        with (
            patch.object(module, "run_pipeline", run_pipeline),
            patch.object(sys, "argv", argv),
            redirect_stdout(StringIO()),
        ):
            module.main()

        config = run_pipeline.call_args.args[0]
        self.assertEqual(config.repo_model, "repo-model")
        self.assertEqual(config.tests_models, ("model-b", "model-c", "model-d"))

    def test_run_group_name_is_independent_of_test_model_order(self) -> None:
        module = load_script("0_run_pipeline.py")

        self.assertEqual(
            module.run_group_name("repo-model", ["model-b", "model-a"]),
            module.run_group_name("repo-model", ["model-a", "model-b"]),
        )

    def test_baseline_generation_script_writes_manifest(self) -> None:
        module = load_script("1_generate_baseline_repo.py")
        manifest = self.root / "baseline.json"
        output_dir = self.root / "baseline"

        with (
            patch.object(module, "run_baseline_generation") as run_baseline_generation,
            patch.object(sys, "argv", ["1_generate_baseline_repo.py", "--output-dir", str(output_dir), "--manifest", str(manifest)]),
            redirect_stdout(StringIO()),
        ):
            module.main()

        config = run_baseline_generation.call_args.args[0]
        self.assertEqual(config.output_dir, output_dir)
        self.assertEqual(config.manifest_path, manifest)

    def test_test_generation_script_writes_manifest(self) -> None:
        module = load_script("2_generate_tests.py")
        manifest = self.root / "tests.json"
        repo_dir = self.root / "repo"
        output_dir = self.root / "tests"

        with (
            patch.object(module, "run_test_generation") as run_test_generation,
            patch.object(
                sys,
                "argv",
                [
                    "2_generate_tests.py",
                    "--repo-dir",
                    str(repo_dir),
                    "--output-dir",
                    str(output_dir),
                    "--manifest",
                    str(manifest),
                    "--max-repairs",
                    "5",
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            module.main()

        config = run_test_generation.call_args.args[0]
        self.assertEqual(config.repo_dir, repo_dir)
        self.assertEqual(config.output_dir, output_dir)
        self.assertEqual(config.manifest_path, manifest)
        self.assertEqual(config.max_repairs, 5)

    def test_evaluation_script_rejects_missing_artifact_directories_before_running(self) -> None:
        module = load_script("3_evaluate_with_pitest.py")
        missing_repo = self.root / "missing-repo"
        tests_dir = self.root / "tests"
        tests_dir.mkdir()

        with (
            patch.object(module, "run_evaluation", side_effect=FileNotFoundError("missing")) as run_evaluation,
            patch.object(
                sys,
                "argv",
                [
                    "3_evaluate_with_pitest.py",
                    "--baseline-repo",
                    str(missing_repo),
                    "--tests-dir",
                    str(tests_dir),
                ],
            ),
        ):
            with self.assertRaises(FileNotFoundError):
                module.main()

        run_evaluation.assert_called_once()

    def test_evaluation_script_passes_cli_args_to_runner(self) -> None:
        module = load_script("3_evaluate_with_pitest.py")
        baseline_repo = self.root / "repo"
        tests_dir = self.root / "tests"
        report_json = self.root / "report.json"
        report_md = self.root / "report.md"
        baseline_repo.mkdir()
        (tests_dir / "src/test/java").mkdir(parents=True)

        with (
            patch.object(module, "run_evaluation") as run_evaluation,
            patch.object(module, "write_comparison_reports") as write_comparison_reports,
            patch.object(
                sys,
                "argv",
                [
                    "3_evaluate_with_pitest.py",
                    "--baseline-repo",
                    str(baseline_repo),
                    "--tests-dir",
                    str(tests_dir),
                    "--report-json",
                    str(report_json),
                    "--report-md",
                    str(report_md),
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            module.main()

        config = run_evaluation.call_args.args[0]
        self.assertEqual(config.baseline_repo, baseline_repo)
        self.assertEqual(config.tests_dir, tests_dir)
        self.assertEqual(config.pitest_report_dir, Path("artifacts/reports/pit-reports"))
        write_comparison_reports.assert_called_once()

    def test_evaluation_script_writes_only_comparison_reports(self) -> None:
        module = load_script("3_evaluate_with_pitest.py")
        baseline_repo = self.root / "repo"
        tests_dir = self.root / "tests"
        baseline_repo.mkdir()
        (tests_dir / "src/test/java").mkdir(parents=True)
        runs = []

        with (
            patch.object(module, "run_evaluation", return_value=runs),
            patch.object(module, "write_comparison_reports") as write_comparison_reports,
            patch.object(
                sys,
                "argv",
                [
                    "3_evaluate_with_pitest.py",
                    "--baseline-repo",
                    str(baseline_repo),
                    "--tests-dir",
                    str(tests_dir),
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            module.main()

        kwargs = write_comparison_reports.call_args.kwargs
        self.assertEqual(kwargs["report_json"], Path("artifacts/reports/comparison_report.json"))
        self.assertEqual(kwargs["report_md"], Path("artifacts/reports/comparison_report.md"))


if __name__ == "__main__":
    unittest.main()
