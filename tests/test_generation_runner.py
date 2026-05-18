from __future__ import annotations

import json
import shutil
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from benchmark_pipeline.generation.runner import (
    BaselineGenerationConfig,
    TestGenerationConfig,
    run_baseline_generation,
    run_test_generation,
)
from benchmark_pipeline.generation.profiles import get_benchmark_profile
from benchmark_pipeline.models import FileArtifact, GeneratedRepo, GeneratedTests


def generated_repo() -> GeneratedRepo:
    return GeneratedRepo(
        project_name="demo",
        description="demo",
        files=[FileArtifact(path="pom.xml", content="<project/>")],
    )


def generated_tests() -> GeneratedTests:
    return GeneratedTests(
        summary="tests",
        files=[
            FileArtifact(
                path="src/test/java/com/example/AppTest.java",
                content=(
                    "package com.example;\n\n"
                    "import org.junit.jupiter.api.Test;\n\n"
                    "import static org.junit.jupiter.api.Assertions.assertTrue;\n\n"
                    "class AppTest {\n"
                    "    @Test\n"
                    "    void generatedTest() {\n"
                    "        assertTrue(true);\n"
                    "    }\n"
                    "}\n"
                ),
            )
        ],
    )


class TestGenerationRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("artifacts/.unit-tests/generation-runner")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_baseline_generation_writes_manifest(self) -> None:
        config = BaselineGenerationConfig(
            model="repo-model",
            project_name="demo-project",
            output_dir=self.root / "baseline",
            manifest_path=self.root / "manifests/baseline.json",
            verify_cmd=["mvn", "test"],
            max_repairs=2,
            benchmark_profile=get_benchmark_profile("library"),
        )

        with (
            patch("benchmark_pipeline.generation.runner.generate_verified_repo", return_value=generated_repo()) as generate_verified_repo,
            redirect_stdout(StringIO()),
        ):
            result = run_baseline_generation(config)

        self.assertEqual(result.project_name, "demo")
        self.assertTrue(config.manifest_path.exists())
        self.assertEqual(json.loads(config.manifest_path.read_text(encoding="utf-8"))["project_name"], "demo")
        self.assertEqual(generate_verified_repo.call_args.kwargs["model"], "repo-model")
        self.assertEqual(generate_verified_repo.call_args.kwargs["verify_cmd"], ["mvn", "test"])
        self.assertEqual(
            generate_verified_repo.call_args.kwargs["benchmark_profile"].profile_id,
            "library",
        )

    def test_test_generation_writes_manifest(self) -> None:
        config = TestGenerationConfig(
            repo_dir=self.root / "baseline",
            output_dir=self.root / "tests",
            model="test-model",
            manifest_path=self.root / "manifests/tests.json",
            max_repairs=4,
            initial_output_dir=self.root / "tests-initial",
        )

        with (
            patch("benchmark_pipeline.generation.runner.generate_tests", return_value=generated_tests()) as generate_tests,
            redirect_stdout(StringIO()),
        ):
            result = run_test_generation(config)

        self.assertEqual(result.summary, "tests")
        self.assertTrue(config.manifest_path.exists())
        self.assertEqual(json.loads(config.manifest_path.read_text(encoding="utf-8"))["summary"], "tests")
        self.assertEqual(generate_tests.call_args.kwargs["repo_dir"], self.root / "baseline")
        self.assertEqual(generate_tests.call_args.kwargs["output_dir"], self.root / "tests")
        self.assertEqual(generate_tests.call_args.kwargs["max_repairs"], 4)
        self.assertEqual(generate_tests.call_args.kwargs["initial_output_dir"], self.root / "tests-initial")


if __name__ == "__main__":
    unittest.main()
