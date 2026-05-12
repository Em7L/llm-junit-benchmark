from __future__ import annotations

import unittest

import _path  # noqa: F401

from benchmark_pipeline.models import FileArtifact, GeneratedRepo, GeneratedTests
from benchmark_pipeline.validation import (
    OutputValidationError,
    validate_generated_repo,
    validate_generated_tests,
)


class TestValidation(unittest.TestCase):
    def test_valid_repo_passes_semantic_validation(self) -> None:
        repo = GeneratedRepo(
            project_name="demo",
            description="demo",
            files=[
                FileArtifact(path="pom.xml", content="<project/>"),
                FileArtifact(path="README.md", content="demo"),
                FileArtifact(path="src/main/java/com/example/App.java", content="class App {}"),
            ],
        )

        validate_generated_repo(repo)

    def test_repo_rejects_duplicate_paths_before_other_errors(self) -> None:
        repo = GeneratedRepo(
            project_name="demo",
            description="demo",
            files=[
                FileArtifact(path="pom.xml", content="one"),
                FileArtifact(path="pom.xml", content="two"),
            ],
        )

        with self.assertRaisesRegex(OutputValidationError, "Duplicate file paths"):
            validate_generated_repo(repo)

    def test_repo_requires_pom_readme_and_main_java(self) -> None:
        cases = [
            (
                GeneratedRepo(
                    project_name="demo",
                    description="demo",
                    files=[
                        FileArtifact(path="README.md", content="demo"),
                        FileArtifact(path="src/main/java/com/example/App.java", content="class App {}"),
                    ],
                ),
                "missing pom.xml",
            ),
            (
                GeneratedRepo(
                    project_name="demo",
                    description="demo",
                    files=[
                        FileArtifact(path="pom.xml", content="<project/>"),
                        FileArtifact(path="README.md", content="demo"),
                    ],
                ),
                "at least one Java source",
            ),
            (
                GeneratedRepo(
                    project_name="demo",
                    description="demo",
                    files=[
                        FileArtifact(path="pom.xml", content="<project/>"),
                        FileArtifact(path="src/main/java/com/example/App.java", content="class App {}"),
                    ],
                ),
                "missing README.md",
            ),
        ]

        for repo, expected_message in cases:
            with self.subTest(expected_message=expected_message):
                with self.assertRaisesRegex(OutputValidationError, expected_message):
                    validate_generated_repo(repo)

    def test_generated_tests_reject_non_test_java_paths(self) -> None:
        tests = GeneratedTests(
            summary="demo",
            files=[
                FileArtifact(path="src/main/java/com/example/AppTest.java", content="class AppTest {}"),
            ],
        )

        with self.assertRaisesRegex(OutputValidationError, "invalid file paths"):
            validate_generated_tests(tests)

    def test_generated_tests_reject_duplicate_paths(self) -> None:
        tests = GeneratedTests(
            summary="demo",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content="one"),
                FileArtifact(path="src/test/java/com/example/AppTest.java", content="two"),
            ],
        )

        with self.assertRaisesRegex(OutputValidationError, "Duplicate file paths"):
            validate_generated_tests(tests)


if __name__ == "__main__":
    unittest.main()
