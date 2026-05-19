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


def test_file_content(class_name: str) -> str:
    return (
        "package com.example;\n\n"
        "import org.junit.jupiter.api.Test;\n\n"
        "import static org.junit.jupiter.api.Assertions.assertTrue;\n\n"
        f"class {class_name} {{\n"
        "    @Test\n"
        "    void generatedTest() {\n"
        "        assertTrue(true);\n"
        "    }\n"
        "}\n"
    )


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
                    content=test_file_content("AppTest"),
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
        self.assertEqual(result.repair_outcome, "repair_not_needed")
        self.assertEqual(result.repair_attempts, 0)
        self.assertEqual(
            (output_dir / "src/test/java/com/example/AppTest.java").read_text(encoding="utf-8"),
            test_file_content("AppTest"),
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
                    content=test_file_content("AppTest"),
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
                    content=test_file_content("AppTest"),
                )
            ],
        )
        repaired = GeneratedTests(
            summary="repaired tests",
            files=[
                FileArtifact(
                    path="src/test/java/com/example/AppTest.java",
                    content=test_file_content("AppTest"),
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
        self.assertEqual(run_maven_tests.call_count, 2)
        self.assertTrue((output_dir / "src/test/java/com/example/AppTest.java").exists())
        semantic_repair_prompt = parse.call_args_list[1].kwargs["user_input"]
        self.assertIn("Here are the repository files (including the failing tests):", semantic_repair_prompt)
        self.assertIn("FILE: src/main/java/com/example/AppTest.java", semantic_repair_prompt)

    def test_generate_tests_fails_after_semantic_repair_budget_is_exhausted(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        invalid = GeneratedTests(
            summary="bad tests",
            files=[
                FileArtifact(
                    path="src/main/java/com/example/AppTest.java",
                    content=test_file_content("AppTest"),
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
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("BrokenTest"))
            ],
        )
        repaired = GeneratedTests(
            summary="repaired tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("AppTest"))
            ],
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", side_effect=[broken, repaired]) as parse,
            patch(
                "benchmark_pipeline.generation.tests_generation.run_maven_tests",
                side_effect=[failed_maven_result(), passed_maven_result(), passed_maven_result()],
            ) as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=1)

        self.assertEqual(result.summary, "repaired tests")
        self.assertEqual(result.repair_outcome, "repair_successful")
        self.assertEqual(result.repair_attempts, 1)
        self.assertEqual(result.repair_reasons, ["verification_failure"])
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(run_maven_tests.call_count, 3)
        repair_prompt = parse.call_args_list[1].kwargs["user_input"]
        self.assertIn("class BrokenTest", repair_prompt)

    def test_generate_tests_skips_full_test_when_test_compile_fails(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        broken = GeneratedTests(
            summary="broken tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("BrokenTest"))
            ],
        )
        compile_failure = MavenResult(
            label="repo",
            exit_code=1,
            status="test_compile_failure",
            status_reason="Test sources did not compile.",
            tests=0,
            failures=0,
            errors=0,
            skipped=0,
            failing_tests=[],
            stdout="compile failed",
            stderr="",
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", return_value=broken),
            patch("benchmark_pipeline.generation.tests_generation.run_maven_tests", return_value=compile_failure) as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=0)

        self.assertIs(result, broken)
        self.assertEqual(run_maven_tests.call_count, 1)
        self.assertEqual(run_maven_tests.call_args_list[0].args[1], ["mvn", "test-compile"])

    def test_generate_tests_merges_partial_verification_repair_with_existing_suite(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        broken = GeneratedTests(
            summary="broken tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("BrokenAppTest")),
                FileArtifact(path="src/test/java/com/example/ServiceTest.java", content=test_file_content("BrokenServiceTest")),
            ],
        )
        partial_repair = GeneratedTests(
            summary="partial repair",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("AppTest")),
            ],
        )

        with (
            patch(
                "benchmark_pipeline.generation.tests_generation.parse_structured_response",
                side_effect=[broken, partial_repair],
            ) as parse,
            patch(
                "benchmark_pipeline.generation.tests_generation.run_maven_tests",
                side_effect=[failed_maven_result(), passed_maven_result(), passed_maven_result()],
            ) as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=1)

        self.assertEqual(result.summary, "partial repair")
        self.assertEqual(result.repair_outcome, "repair_successful")
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(run_maven_tests.call_count, 3)
        self.assertTrue((output_dir / "src/test/java/com/example/AppTest.java").exists())
        self.assertTrue((output_dir / "src/test/java/com/example/ServiceTest.java").exists())
        self.assertEqual(
            (output_dir / "src/test/java/com/example/AppTest.java").read_text(encoding="utf-8"),
            test_file_content("AppTest"),
        )
        self.assertEqual(
            (output_dir / "src/test/java/com/example/ServiceTest.java").read_text(encoding="utf-8"),
            test_file_content("BrokenServiceTest"),
        )

    def test_generate_tests_keeps_merged_suite_when_partial_repair_still_fails(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        broken = GeneratedTests(
            summary="broken tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("BrokenAppTest")),
                FileArtifact(path="src/test/java/com/example/ServiceTest.java", content=test_file_content("BrokenServiceTest")),
            ],
        )
        partial_repair = GeneratedTests(
            summary="partial repair",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("AppTest")),
            ],
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", side_effect=[broken, partial_repair]) as parse,
            patch("benchmark_pipeline.generation.tests_generation.run_maven_tests", return_value=failed_maven_result()) as run_maven_tests,
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=1)

        self.assertEqual(result.summary, "partial repair")
        self.assertEqual(result.repair_outcome, "repair_no_improvement")
        self.assertEqual(result.repair_attempts, 1)
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(run_maven_tests.call_count, 2)
        self.assertEqual(
            (output_dir / "src/test/java/com/example/AppTest.java").read_text(encoding="utf-8"),
            test_file_content("AppTest"),
        )
        self.assertTrue((output_dir / "src/test/java/com/example/ServiceTest.java").exists())

    def test_generate_tests_classifies_partial_repair_improvement(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        broken = GeneratedTests(
            summary="broken tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("BrokenTest"))
            ],
        )
        repaired = GeneratedTests(
            summary="still failing tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("LessBrokenTest"))
            ],
        )
        initial_failure = MavenResult(
            label="repo",
            exit_code=1,
            status="test_failures",
            status_reason="One or more tests failed.",
            tests=4,
            failures=4,
            errors=0,
            skipped=0,
            failing_tests=[],
            stdout="",
            stderr="",
        )
        improved_failure = MavenResult(
            label="repo",
            exit_code=1,
            status="test_failures",
            status_reason="One or more tests failed.",
            tests=4,
            failures=3,
            errors=0,
            skipped=0,
            failing_tests=[],
            stdout="",
            stderr="",
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", side_effect=[broken, repaired]),
            patch(
                "benchmark_pipeline.generation.tests_generation.run_maven_tests",
                side_effect=[passed_maven_result(), initial_failure, passed_maven_result(), improved_failure],
            ),
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=1)

        self.assertEqual(result.repair_outcome, "repair_partially_improved")

    def test_generate_tests_keeps_last_good_suite_when_repair_regresses_to_compile_failure(self) -> None:
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        output_dir = self.root / "generated-tests"
        initial = GeneratedTests(
            summary="initial failing but runnable tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("InitialTest"))
            ],
        )
        regressed = GeneratedTests(
            summary="regressed compile-failing tests",
            files=[
                FileArtifact(path="src/test/java/com/example/AppTest.java", content=test_file_content("RegressedTest"))
            ],
        )
        initial_failure = MavenResult(
            label="repo",
            exit_code=1,
            status="test_failures",
            status_reason="One or more tests failed.",
            tests=4,
            failures=4,
            errors=0,
            skipped=0,
            failing_tests=[],
            stdout="",
            stderr="",
        )
        compile_failure = MavenResult(
            label="repo",
            exit_code=1,
            status="test_compile_failure",
            status_reason="Test sources did not compile.",
            tests=0,
            failures=0,
            errors=0,
            skipped=0,
            failing_tests=[],
            stdout="compile failed",
            stderr="",
        )

        with (
            patch("benchmark_pipeline.generation.tests_generation.parse_structured_response", side_effect=[initial, regressed]),
            patch(
                "benchmark_pipeline.generation.tests_generation.run_maven_tests",
                side_effect=[passed_maven_result(), initial_failure, compile_failure],
            ),
            redirect_stdout(StringIO()),
        ):
            result = generate_tests(repo_dir=repo_dir, output_dir=output_dir, model="test-model", max_repairs=1)

        self.assertIs(result, initial)
        self.assertEqual(result.repair_outcome, "repair_no_improvement")
        self.assertEqual(
            (output_dir / "src/test/java/com/example/AppTest.java").read_text(encoding="utf-8"),
            test_file_content("InitialTest"),
        )

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
