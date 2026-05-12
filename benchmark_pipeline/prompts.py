from __future__ import annotations

"""Prompt builders for repository generation and test generation."""

import textwrap
from pathlib import Path

from benchmark_pipeline.fs_utils import repo_snapshot, tree_listing


def build_repo_prompt(project_name: str | None = None) -> str:
    explicit_name = project_name or "generated-java-app"
    return textwrap.dedent(
        f"""
        Build a complete, small Maven repository for JDK 21.

        Requirements:
        - Educational Java app with moderate complexity.
        - Choose the application domain yourself.
        - Use 6-10 production classes under a coherent domain model.
        - The app should include orchestration logic plus focused helper/domain classes.
        - Maven project with `pom.xml`.
        - Java source under `src/main/java`.
        - Include JUnit 5, Maven Surefire, JaCoCo, and Maven Exec plugin config in `pom.xml`, but do not include any tests.
        - JaCoCo should generate XML coverage output during `mvn test`.
        - Configure the Maven Exec plugin so the app can be run with `mvn exec:java`.
        - Keep the code understandable enough that another agent can infer expected behavior and write tests.
        - The repository must compile on JDK 21.
        - The repository must pass `mvn test` with zero failing tests.
        - All returned files must be mutually consistent and compile together.
        - Do not reference classes, methods, constructors, fields, or imports that are not defined in the returned repository.
        - Use package names and filenames consistent with the project.
        - Ensure every package declaration matches its file path.
        - Prefer deterministic logic over IO-heavy code.
        - Include meaningful branching and validation logic.
        - Include at least one collection-based workflow.
        - Include at least one formatter/parser/translator style class and one rule/validation class.
        - Include at least one edge-case-heavy method with 3 or more meaningful scenarios.
        - Avoid trivial wrappers whose only purpose is to inflate class count.
        - Avoid external services, databases, files, sockets, threads, or frameworks.
        - You may pick any suitable domain.
        - Include a short `README.md`.
        - Suggested project name: `{explicit_name}`. Adjust it if a better name matches the chosen domain.
        """
    ).strip()


def build_repo_repair_prompt(repo_root: Path, project_name: str | None, build_output: str) -> str:
    snapshot = repo_snapshot(repo_root, include_extensions={".java", ".xml", ".md"})
    tree = tree_listing(repo_root)
    explicit_name = project_name or "generated-java-app"
    return textwrap.dedent(
        f"""
        The previously generated Maven/JDK21 repository did not compile or pass `mvn test`.

        Suggested project name: `{explicit_name}`.

        Current repository tree:
        {tree}

        Current repository files:
        {snapshot}

        Maven/compiler output:
        ```
        {build_output}
        ```

        Return a corrected full repository.

        Requirements:
        - Return the complete repository as full file contents, not partial patches.
        - Preserve the same overall project idea unless the compiler errors force a structural correction.
        - Fix all compilation, packaging, import, and reference inconsistencies.
        - Ensure the returned repository passes `mvn test`.
        - Do not reference classes, methods, constructors, fields, or imports that are not defined in the returned repository.
        - Ensure package declarations, imports, file paths, and the Maven `mainClass` are all mutually consistent.
        """
    ).strip()


def build_test_prompt(repo_root: Path) -> str:
    snapshot = repo_snapshot(repo_root, include_extensions={".java", ".xml", ".md"})
    tree = tree_listing(repo_root)
    return textwrap.dedent(
        f"""
        Here is the repository tree:
        {tree}

        Here are the repository files:
        {snapshot}

        Generate a JUnit 5 test suite for this Maven/JDK21 project.

        Requirements:
        - Return only repository-relative test files to add to the repo.
        - Put tests under `src/test/java`.
        - Do not modify production code.
        - Assume `pom.xml` already contains JUnit 5 and Surefire.
        - Ensure the test files compile against the provided repository as-is.
        - Do not invent classes, methods, constructors, or fields that do not exist in the repository snapshot.
        - Ensure package declarations, imports, and file paths are consistent.
        - Prefer behavior-focused tests, not implementation-detail tests.
        - Cover normal cases, boundary cases, invalid-input cases, and cross-class workflow behavior where applicable.
        - Target meaningful branch coverage, not just method invocation coverage.
        - Add tests that are likely to detect semantic mistakes in formulas, thresholds, validation rules, and formatting.
        - Keep the suite deterministic.
        """
    ).strip()
