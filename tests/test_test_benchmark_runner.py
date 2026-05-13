from __future__ import annotations

import json
import shutil
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from benchmark_pipeline.models import FileArtifact, GeneratedTests
from benchmark_pipeline.generation.benchmark_runner import TestBenchmarkConfig, run_test_generation_benchmark


class TestTestBenchmarkRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("artifacts/.unit-tests/test-benchmark-runner")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_benchmark_writes_manifest_for_successful_model(self) -> None:
        generated = GeneratedTests(
            summary="tests",
            files=[FileArtifact(path="src/test/java/com/example/AppTest.java", content="class AppTest {}")],
        )
        config = TestBenchmarkConfig(
            repo_dir=self.root / "repo",
            output_dir=self.root / "benchmarks",
            manifest_dir=self.root / "manifests",
            models=["model-a"],
        )

        with (
            patch("benchmark_pipeline.generation.benchmark_runner.generate_tests", return_value=generated) as generate_tests,
            redirect_stdout(StringIO()),
        ):
            results = run_test_generation_benchmark(config)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].passed)
        self.assertEqual(results[0].model, "model-a")
        self.assertEqual(generate_tests.call_args.kwargs["output_dir"], self.root / "benchmarks/model-a")
        manifest = self.root / "manifests/model-a_tests.json"
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["summary"], "tests")

    def test_benchmark_records_failed_model_and_continues(self) -> None:
        generated = GeneratedTests(
            summary="tests",
            files=[FileArtifact(path="src/test/java/com/example/AppTest.java", content="class AppTest {}")],
        )
        config = TestBenchmarkConfig(
            repo_dir=self.root / "repo",
            output_dir=self.root / "benchmarks",
            manifest_dir=self.root / "manifests",
            models=["bad-model", "good-model"],
        )

        with (
            patch(
                "benchmark_pipeline.generation.benchmark_runner.generate_tests",
                side_effect=[RuntimeError("generation failed"), generated],
            ),
            redirect_stdout(StringIO()),
        ):
            results = run_test_generation_benchmark(config)

        self.assertEqual([result.model for result in results], ["bad-model", "good-model"])
        self.assertFalse(results[0].passed)
        self.assertEqual(results[0].error, "generation failed")
        self.assertTrue(results[1].passed)
        self.assertFalse((self.root / "manifests/bad-model_tests.json").exists())
        self.assertTrue((self.root / "manifests/good-model_tests.json").exists())


if __name__ == "__main__":
    unittest.main()
