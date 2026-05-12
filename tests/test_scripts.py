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

from benchmark_pipeline.evaluation import EvaluationOutcome
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
        self.assertEqual(config.tests_model, "tests-model")
        self.assertEqual(config.project_name, "demo-project")
        self.assertEqual(config.maven_cmd, ["mvn", "verify"])
        self.assertEqual(config.max_repairs, 3)

    def test_baseline_generation_script_writes_manifest(self) -> None:
        module = load_script("1_generate_baseline_repo.py")
        generated_repo = repo()
        manifest = self.root / "baseline.json"
        output_dir = self.root / "baseline"

        with (
            patch.object(module, "generate_verified_repo", return_value=generated_repo) as generate_verified_repo,
            patch.object(sys, "argv", ["1_generate_baseline_repo.py", "--output-dir", str(output_dir), "--manifest", str(manifest)]),
            redirect_stdout(StringIO()),
        ):
            module.main()

        self.assertTrue(manifest.exists())
        self.assertEqual(generate_verified_repo.call_args.kwargs["output_dir"], output_dir)

    def test_test_generation_script_writes_manifest(self) -> None:
        module = load_script("2_generate_tests.py")
        generated_tests = tests()
        manifest = self.root / "tests.json"
        repo_dir = self.root / "repo"
        output_dir = self.root / "tests"

        with (
            patch.object(module, "generate_tests", return_value=generated_tests) as generate_tests,
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
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            module.main()

        self.assertTrue(manifest.exists())
        self.assertEqual(generate_tests.call_args.kwargs["repo_dir"], repo_dir)
        self.assertEqual(generate_tests.call_args.kwargs["output_dir"], output_dir)

    def test_evaluation_script_rejects_missing_artifact_directories_before_running(self) -> None:
        module = load_script("3_evaluate_with_pitest.py")
        missing_repo = self.root / "missing-repo"
        tests_dir = self.root / "tests"
        tests_dir.mkdir()

        with (
            patch.object(module, "evaluate_repositories") as evaluate_repositories,
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

        evaluate_repositories.assert_not_called()

    def test_evaluation_script_writes_json_and_markdown_reports(self) -> None:
        module = load_script("3_evaluate_with_pitest.py")
        baseline_repo = self.root / "repo"
        tests_dir = self.root / "tests"
        report_json = self.root / "report.json"
        report_md = self.root / "report.md"
        baseline_repo.mkdir()
        tests_dir.mkdir()
        outcome = EvaluationOutcome(
            baseline_result=passed_maven(),
            baseline_coverage=None,
            pitest_result=None,
            disabled_tests=[],
        )

        with (
            patch.object(module, "evaluate_repositories", return_value=outcome),
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

        self.assertTrue(report_json.exists())
        self.assertTrue(report_md.exists())
        self.assertIn("Mutation Evaluation Report", report_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
