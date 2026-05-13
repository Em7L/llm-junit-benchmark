from __future__ import annotations

import shutil
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from benchmark_pipeline.models import FileArtifact, GeneratedRepo, GeneratedTests, MavenResult
from benchmark_pipeline.generation.repo_generation import generate_verified_repo
from benchmark_pipeline.generation.tests_generation import generate_tests


def passed_maven_result() -> MavenResult:
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


def failed_maven_result() -> MavenResult:
    return MavenResult(
        label="repo",
        exit_code=1,
        status="main_compile_failure",
        status_reason="Main sources did not compile.",
        tests=0,
        failures=0,
        errors=0,
        skipped=0,
        failing_tests=[],
        stdout="compile failed",
        stderr="",
    )


def valid_repo(project_name: str = "demo") -> GeneratedRepo:
    return GeneratedRepo(
        project_name=project_name,
        description="demo",
        files=[
            FileArtifact(path="pom.xml", content="<project/>"),
            FileArtifact(path="README.md", content="demo"),
            FileArtifact(path="src/main/java/com/example/App.java", content="class App {}"),
        ],
    )


class TestGenerationOrchestration(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("artifacts/.unit-tests/generation")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_generate_tests_writes_valid_model_output(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        generated = GeneratedTests(
            summary="tests",
            files=[
                FileArtifact(
                    path="src/test/java/com/example/AppTest.java",
                    content="class AppTest {}",
                )
            ],
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", return_value=generated),
            patch("benchmark_pipeline.generation.tests_generation.run_maven_tests", return_value=passed_maven_result()),
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model")

        self.assertIs(result, generated)
        self.assertEqual(
            (output_dir / "src/test/java/com/example/AppTest.java").read_text(encoding="utf-8"),
            "class AppTest {}",
        )

    def test_generate_tests_rejects_invalid_model_output_before_overwriting_previous_output(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        output_dir.mkdir()
        sentinel = output_dir / "keep.txt"
        sentinel.write_text("previous output", encoding="utf-8")
        generated = GeneratedTests(
            summary="bad tests",
            files=[
                FileArtifact(
                    path="src/main/java/com/example/AppTest.java",
                    content="class AppTest {}",
                )
            ],
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", return_value=generated),
            redirect_stdout(StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "failed semantic validation after repair attempts"):
                generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model")

        self.assertTrue(sentinel.exists())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "previous output")

    def test_generate_tests_repairs_semantically_invalid_output(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        invalid = GeneratedTests(
            summary="bad tests",
            files=[
                FileArtifact(
                    path="src/main/java/com/example/AppTest.java",
                    content="class AppTest {}",
                )
            ],
        )
        repaired = GeneratedTests(
            summary="repaired tests",
            files=[
                FileArtifact(
                    path="src/test/java/com/example/AppTest.java",
                    content="class AppTest {}",
                )
            ],
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", side_effect=[invalid, repaired]) as parse,
            patch("benchmark_pipeline.generation.tests_generation.run_maven_tests", return_value=passed_maven_result()) as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=1)

        self.assertIs(result, repaired)
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(run_maven_tests.call_count, 1)
        self.assertTrue((output_dir / "src/test/java/com/example/AppTest.java").exists())

    def test_generate_tests_fails_after_semantic_repair_budget_is_exhausted(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        invalid = GeneratedTests(
            summary="bad tests",
            files=[
                FileArtifact(
                    path="src/main/java/com/example/AppTest.java",
                    content="class AppTest {}",
                )
            ],
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", return_value=invalid) as parse,
            patch("benchmark_pipeline.generation.tests_generation.run_maven_tests") as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "failed semantic validation after repair attempts"):
                generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=1)

        self.assertEqual(parse.call_count, 2)
        run_maven_tests.assert_not_called()
        self.assertFalse(output_dir.exists())

    def test_generate_tests_repairs_after_failed_maven_verification(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        broken = GeneratedTests(
            summary="broken tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content="class BrokenTest {}")
            ],
        )
        repaired = GeneratedTests(
            summary="repaired tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content="class AppTest {}")
            ],
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", side_effect=[broken, repaired]) as parse,
            patch("benchmark_pipeline.generation.tests_generation.run_maven_tests", side_effect=[failed_maven_result(), passed_maven_result()]) as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=1)

        self.assertIs(result, repaired)
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(run_maven_tests.call_count, 2)
        repair_prompt = parse.call_args_list[1].kwargs["user_input"]
        self.assertIn("class BrokenTest {}", repair_prompt)

    def test_generate_tests_retries_repair_that_drops_existing_test_files(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        broken = GeneratedTests(
            summary="broken tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content="class BrokenAppTest {}"),
                FileArtifact(path="src/test/java/com/example/ServiceTest.java", content="class BrokenServiceTest {}"),
            ],
        )
        incomplete_repair = GeneratedTests(
            summary="incomplete repair",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content="class AppTest {}"),
            ],
        )
        complete_repair = GeneratedTests(
            summary="complete repair",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content="class AppTest {}"),
                FileArtifact(path="src/test/java/com/example/ServiceTest.java", content="class ServiceTest {}"),
            ],
        )

        with (
            patch(
                "benchmark_pipeline.generation.tests_generation.parse_structured_response",
                side_effect=[broken, incomplete_repair, complete_repair],
            ) as parse,
            patch(
                "benchmark_pipeline.generation.tests_generation.run_maven_tests",
                side_effect=[failed_maven_result(), failed_maven_result(), passed_maven_result()],
            ) as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=2)

        self.assertIs(result, complete_repair)
        self.assertEqual(parse.call_count, 3)
        self.assertEqual(run_maven_tests.call_count, 3)
        self.assertTrue((output_dir / "src/test/java/com/example/AppTest.java").exists())
        self.assertTrue((output_dir / "src/test/java/com/example/ServiceTest.java").exists())

    def test_generate_tests_keeps_last_complete_suite_when_final_repair_drops_files(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        broken = GeneratedTests(
            summary="broken tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content="class BrokenAppTest {}"),
                FileArtifact(path="src/test/java/com/example/ServiceTest.java", content="class BrokenServiceTest {}"),
            ],
        )
        incomplete_repair = GeneratedTests(
            summary="incomplete repair",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content="class AppTest {}"),
            ],
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", side_effect=[broken, incomplete_repair]) as parse,
            patch("benchmark_pipeline.generation.tests_generation.run_maven_tests", return_value=failed_maven_result()) as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=1)

        self.assertIs(result, broken)
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(run_maven_tests.call_count, 1)
        self.assertEqual(
            (output_dir / "src/test/java/com/example/AppTest.java").read_text(encoding="utf-8"),
            "class BrokenAppTest {}",
        )
        self.assertTrue((output_dir / "src/test/java/com/example/ServiceTest.java").exists())

    def test_generate_verified_repo_repairs_after_failed_build(self) -> None:
        output_dir = self.root / "repo"
        broken = valid_repo("broken")
        repaired = valid_repo("repaired")

        with (
            patch("benchmark_pipeline.generation.repo_generation.parse_structured_response", side_effect=[broken, repaired]) as parse,
            patch("benchmark_pipeline.generation.repo_generation.run_maven_tests", side_effect=[failed_maven_result(), passed_maven_result()]),
            redirect_stdout(StringIO()),
        ):
            result = generate_verified_repo(
                model="test-model",
                project_name="demo",
                output_dir=output_dir,
                max_repairs=1,
                verify_cmd=["mvn", "test"],
            )

        self.assertIs(result, repaired)
        self.assertEqual(parse.call_count, 2)
        self.assertEqual((output_dir / "README.md").read_text(encoding="utf-8"), "demo")

    def test_generate_verified_repo_repairs_after_semantically_invalid_output(self) -> None:
        output_dir = self.root / "repo"
        invalid = GeneratedRepo(
            project_name="invalid",
            description="missing readme",
            files=[
                FileArtifact(path="pom.xml", content="<project/>"),
                FileArtifact(path="src/main/java/com/example/App.java", content="class App {}"),
            ],
        )
        repaired = valid_repo("repaired")

        with (
            patch("benchmark_pipeline.generation.repo_generation.parse_structured_response", side_effect=[invalid, repaired]) as parse,
            patch("benchmark_pipeline.generation.repo_generation.run_maven_tests", return_value=passed_maven_result()) as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            result = generate_verified_repo(
                model="test-model",
                project_name="demo",
                output_dir=output_dir,
                max_repairs=1,
                verify_cmd=["mvn", "test"],
            )

        self.assertIs(result, repaired)
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(run_maven_tests.call_count, 1)

    def test_generate_verified_repo_fails_after_repair_budget_is_exhausted(self) -> None:
        output_dir = self.root / "repo"

        with (
            patch("benchmark_pipeline.generation.repo_generation.parse_structured_response", return_value=valid_repo()),
            patch("benchmark_pipeline.generation.repo_generation.run_maven_tests", return_value=failed_maven_result()),
            redirect_stdout(StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "failed verification after repair attempts"):
                generate_verified_repo(
                    model="test-model",
                    project_name="demo",
                    output_dir=output_dir,
                    max_repairs=0,
                    verify_cmd=["mvn", "test"],
                )

    def test_generate_verified_repo_fails_after_semantic_repair_budget_is_exhausted(self) -> None:
        output_dir = self.root / "repo"
        invalid = GeneratedRepo(
            project_name="invalid",
            description="missing readme",
            files=[
                FileArtifact(path="pom.xml", content="<project/>"),
                FileArtifact(path="src/main/java/com/example/App.java", content="class App {}"),
            ],
        )

        with (
            patch("benchmark_pipeline.generation.repo_generation.parse_structured_response", return_value=invalid) as parse,
            patch("benchmark_pipeline.generation.repo_generation.run_maven_tests") as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "failed semantic validation after repair attempts"):
                generate_verified_repo(
                    model="test-model",
                    project_name="demo",
                    output_dir=output_dir,
                    max_repairs=1,
                    verify_cmd=["mvn", "test"],
                )

        self.assertEqual(parse.call_count, 2)
        run_maven_tests.assert_not_called()
        self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
