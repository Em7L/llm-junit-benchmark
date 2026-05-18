from __future__ import annotations

"""Semantic validators for model outputs before they are written or executed."""

from collections import Counter
import re

from benchmark_pipeline.models import GeneratedRepo, GeneratedTests


class OutputValidationError(ValueError):
    """Raised when a parsed model output is structurally valid but semantically unusable."""


def validate_generated_repo(repo: GeneratedRepo) -> None:
    if not repo.files:
        raise OutputValidationError("Generated repository contains no files.")

    paths = [artifact.path for artifact in repo.files]
    _validate_unique_paths(paths, "repository")

    if "pom.xml" not in paths:
        raise OutputValidationError("Generated repository is missing pom.xml.")

    if not any(path.startswith("src/main/java/") and path.endswith(".java") for path in paths):
        raise OutputValidationError("Generated repository must include at least one Java source file under src/main/java.")

    if not any(path == "README.md" for path in paths):
        raise OutputValidationError("Generated repository is missing README.md.")


def validate_generated_tests(tests: GeneratedTests) -> None:
    if not tests.files:
        raise OutputValidationError("Generated test suite contains no files.")

    paths = [artifact.path for artifact in tests.files]
    _validate_unique_paths(paths, "test suite")

    invalid_paths = [
        path for path in paths if not path.startswith("src/test/java/") or not path.endswith(".java")
    ]
    if invalid_paths:
        preview = ", ".join(invalid_paths[:3])
        raise OutputValidationError(
            "Generated test suite contains invalid file paths. "
            f"Expected only Java test files under src/test/java, got: {preview}"
        )

    contents = [_strip_java_comments(artifact.content) for artifact in tests.files]

    if not any(_contains_junit_test_annotation(content) for content in contents):
        raise OutputValidationError(
            "Generated test suite does not appear to contain any JUnit test methods. "
            "Include executable JUnit 5 tests annotated with @Test or a related JUnit 5 test annotation."
        )

    if not any(_contains_assertion_or_failure_check(content) for content in contents):
        raise OutputValidationError(
            "Generated test suite does not appear to contain any assertions or failure checks. "
            "Return behavior-checking tests, not empty placeholder methods."
        )


def _validate_unique_paths(paths: list[str], label: str) -> None:
    duplicates = sorted(path for path, count in Counter(paths).items() if count > 1)
    if duplicates:
        preview = ", ".join(duplicates[:3])
        raise OutputValidationError(f"Duplicate file paths found in generated {label}: {preview}")


def _strip_java_comments(text: str) -> str:
    without_block_comments = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//.*", "", without_block_comments)


def _contains_junit_test_annotation(content: str) -> bool:
    return bool(re.search(r"@(?:Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b", content))


def _contains_assertion_or_failure_check(content: str) -> bool:
    return bool(
        re.search(r"\b(?:assert[A-Za-z0-9_]*|assertThat|fail)\s*\(", content)
        or re.search(r"\bAssertions\.(?:assert[A-Za-z0-9_]*|assertThat|fail)\s*\(", content)
    )
