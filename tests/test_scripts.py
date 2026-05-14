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


def load_script(filename: str) -> ModuleType:
    script_path = Path(filename).resolve()
    module_name = filename.replace(".py", "").replace("_", "-") + "-test-module"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load script: {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
            "--profile-id",
            "library",
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
        self.assertEqual(config.benchmark_profile.profile_id, "library")
        self.assertEqual(config.project_name, "demo-project")
        self.assertEqual(config.maven_cmd, ["mvn", "verify"])
        self.assertEqual(config.max_repairs, 3)

    def test_run_pipeline_script_uses_next_preserved_run_directory_by_default(self) -> None:
        module = load_script("0_run_pipeline.py")
        run_pipeline = Mock()
        output_root = self.root / "runs"
        existing_run = (
            output_root
            / "profile-library__repo-repo-model__tests-test-model"
            / "run-001"
        )
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
                    "--profile-id",
                    "library",
                    "--output-root",
                    str(output_root),
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            module.main()

        config = run_pipeline.call_args.args[0]
        expected_run = output_root / "profile-library__repo-repo-model__tests-test-model" / "run-002"
        self.assertEqual(config.baseline_repo, expected_run / "baseline_repo")
        self.assertEqual(config.tests_dir, expected_run / "generated_tests")
        self.assertEqual(config.profile_manifest, expected_run / "manifests/benchmark_profile.json")
        self.assertEqual(config.report_md, expected_run / "reports/comparison_report.md")

    def test_run_pipeline_script_accepts_multiple_test_models(self) -> None:
        module = load_script("0_run_pipeline.py")
        run_pipeline = Mock()
        argv = [
            "0_run_pipeline.py",
            "--repo-model",
            "repo-model",
            "--profile-id",
            "library",
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
        self.assertEqual(config.benchmark_profile.profile_id, "library")

    def test_run_group_name_is_independent_of_test_model_order(self) -> None:
        module = load_script("0_run_pipeline.py")

        self.assertEqual(
            module.run_group_name("library", "repo-model", ["model-b", "model-a"]),
            module.run_group_name("library", "repo-model", ["model-a", "model-b"]),
        )


if __name__ == "__main__":
    unittest.main()
