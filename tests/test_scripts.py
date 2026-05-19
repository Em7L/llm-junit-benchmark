from __future__ import annotations

import importlib.util
import shutil
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
import json
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
        self.root = Path("run_outputs/.unit-tests/scripts")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_run_pipeline_script_builds_config_from_cli_args(self) -> None:
        module = load_script("run_pipeline.py")
        run_pipeline = Mock()
        argv = [
            "run_pipeline.py",
            "--model",
            "default-model",
            "--repo-model",
            "repo-model",
            "--tests-model",
            "tests-model",
            "--profile-id",
            "low",
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
        self.assertEqual(config.benchmark_profile.profile_id, "low")
        self.assertEqual(config.project_name, "demo-project")
        self.assertEqual(config.maven_cmd, ["mvn", "verify"])
        self.assertEqual(config.max_repairs, 3)

    def test_run_pipeline_script_uses_next_preserved_run_directory_by_default(self) -> None:
        module = load_script("run_pipeline.py")
        run_pipeline = Mock()
        output_root = self.root / "runs"
        existing_run = (
            output_root
            / "profile-low__repo-repo-model__tests-test-model"
            / "run-001"
        )
        existing_run.mkdir(parents=True)

        with (
            patch.object(module, "run_pipeline", run_pipeline),
            patch.object(
                sys,
                "argv",
                [
                    "run_pipeline.py",
                    "--repo-model",
                    "repo-model",
                    "--tests-model",
                    "test-model",
                    "--profile-id",
                    "low",
                    "--output-root",
                    str(output_root),
                ],
            ),
            redirect_stdout(StringIO()),
        ):
            module.main()

        config = run_pipeline.call_args.args[0]
        expected_run = output_root / "profile-low__repo-repo-model__tests-test-model" / "run-002"
        self.assertEqual(config.baseline_repo, expected_run / "baseline_repo")
        self.assertEqual(config.tests_dir, expected_run / "generated_tests")
        self.assertEqual(config.profile_manifest, expected_run / "manifests/benchmark_profile.json")
        self.assertEqual(config.report_md, expected_run / "reports/comparison_report.md")

    def test_run_pipeline_script_accepts_multiple_test_models(self) -> None:
        module = load_script("run_pipeline.py")
        run_pipeline = Mock()
        argv = [
            "run_pipeline.py",
            "--repo-model",
            "repo-model",
            "--profile-id",
            "low",
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
        self.assertEqual(config.benchmark_profile.profile_id, "low")

    def test_run_group_name_is_independent_of_test_model_order(self) -> None:
        module = load_script("run_pipeline.py")

        self.assertEqual(
            module.run_group_name("low", "repo-model", ["model-b", "model-a"]),
            module.run_group_name("low", "repo-model", ["model-a", "model-b"]),
        )

    def test_run_experiment_matrix_builds_pipeline_config_for_missing_runs(self) -> None:
        module = load_script("run_experiment_matrix.py")
        run_pipeline = Mock()
        output_root = self.root / "runs"
        existing_run = (
            output_root
            / "profile-low__repo-gpt-5.4-mini__tests-deepseek-v4-flash_gpt-5.4-mini"
            / "run-001"
        )
        existing_run.mkdir(parents=True)

        argv = [
            "run_experiment_matrix.py",
            "--profile-ids",
            "low",
            "--repo-models",
            "gpt-5.4-mini",
            "--tests-models",
            "gpt-5.4-mini",
            "deepseek-v4-flash",
            "--repetitions",
            "2",
            "--output-root",
            str(output_root),
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
        expected_run = existing_run.parent / "run-002"
        self.assertEqual(config.repo_model, "gpt-5.4-mini")
        self.assertEqual(config.tests_models, ("gpt-5.4-mini", "deepseek-v4-flash"))
        self.assertEqual(config.benchmark_profile.profile_id, "low")
        self.assertEqual(config.baseline_repo, expected_run / "baseline_repo")
        self.assertEqual(config.report_md, expected_run / "reports/comparison_report.md")
        self.assertEqual(config.maven_cmd, ["mvn", "verify"])
        self.assertEqual(config.max_repairs, 3)
        summary = json.loads((output_root / "experiment_timing_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["executed_runs"], 1)
        self.assertEqual(summary["runs"][0]["status"], "completed")
        self.assertEqual(summary["runs"][0]["run_dir"], expected_run.as_posix())
        self.assertIn("total_duration_hms", summary)

    def test_run_experiment_matrix_skips_satisfied_conditions(self) -> None:
        module = load_script("run_experiment_matrix.py")
        run_pipeline = Mock()
        output_root = self.root / "runs"
        group_dir = (
            output_root
            / "profile-low__repo-gpt-5.4-mini__tests-gpt-5.4-mini"
        )
        (group_dir / "run-001").mkdir(parents=True)
        (group_dir / "run-002").mkdir(parents=True)

        argv = [
            "run_experiment_matrix.py",
            "--profile-ids",
            "low",
            "--repo-models",
            "gpt-5.4-mini",
            "--tests-models",
            "gpt-5.4-mini",
            "--repetitions",
            "2",
            "--output-root",
            str(output_root),
        ]

        with (
            patch.object(module, "run_pipeline", run_pipeline),
            patch.object(sys, "argv", argv),
            redirect_stdout(StringIO()),
        ):
            module.main()

        run_pipeline.assert_not_called()
        summary = json.loads((output_root / "experiment_timing_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["executed_runs"], 0)
        self.assertEqual(summary["planned_missing_runs"], 0)

    def test_run_experiment_matrix_dry_run_does_not_execute_pipeline(self) -> None:
        module = load_script("run_experiment_matrix.py")
        run_pipeline = Mock()

        argv = [
            "run_experiment_matrix.py",
            "--profile-ids",
            "low",
            "--repo-models",
            "gpt-5.4-mini",
            "--tests-models",
            "gpt-5.4-mini",
            "--repetitions",
            "1",
            "--output-root",
            str(self.root / "runs"),
            "--dry-run",
        ]

        with (
            patch.object(module, "run_pipeline", run_pipeline),
            patch.object(sys, "argv", argv),
            redirect_stdout(StringIO()),
        ):
            module.main()

        run_pipeline.assert_not_called()
        summary = json.loads(((self.root / "runs") / "experiment_timing_summary.json").read_text(encoding="utf-8"))
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["executed_runs"], 0)

    def test_run_experiment_matrix_deletes_invalid_run_and_stops_on_quota_error(self) -> None:
        module = load_script("run_experiment_matrix.py")
        output_root = self.root / "runs"
        run_pipeline = Mock(side_effect=RuntimeError("insufficient_quota: no credits left"))

        argv = [
            "run_experiment_matrix.py",
            "--profile-ids",
            "low",
            "--repo-models",
            "gpt-5.4-mini",
            "--tests-models",
            "gpt-5.4-mini",
            "--repetitions",
            "1",
            "--output-root",
            str(output_root),
        ]

        with (
            patch.object(module, "run_pipeline", run_pipeline),
            patch.object(sys, "argv", argv),
            redirect_stdout(StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "insufficient_quota"):
                module.main()

        failed_run = output_root / "profile-low__repo-gpt-5.4-mini__tests-gpt-5.4-mini" / "run-001"
        self.assertFalse(failed_run.exists())
        summary = json.loads((output_root / "experiment_timing_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["executed_runs"], 1)
        self.assertEqual(summary["runs"][0]["status"], "aborted_provider_limit")

    def test_run_experiment_matrix_continue_on_error_does_not_override_quota_stop(self) -> None:
        module = load_script("run_experiment_matrix.py")
        output_root = self.root / "runs"
        run_pipeline = Mock(side_effect=RuntimeError("rate limit reached"))

        argv = [
            "run_experiment_matrix.py",
            "--profile-ids",
            "low",
            "--repo-models",
            "gpt-5.4-mini",
            "--tests-models",
            "gpt-5.4-mini",
            "--repetitions",
            "1",
            "--output-root",
            str(output_root),
            "--continue-on-error",
        ]

        with (
            patch.object(module, "run_pipeline", run_pipeline),
            patch.object(sys, "argv", argv),
            redirect_stdout(StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "rate limit reached"):
                module.main()

        failed_run = output_root / "profile-low__repo-gpt-5.4-mini__tests-gpt-5.4-mini" / "run-001"
        self.assertFalse(failed_run.exists())
        summary = json.loads((output_root / "experiment_timing_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["runs"][0]["status"], "aborted_provider_limit")


if __name__ == "__main__":
    unittest.main()
