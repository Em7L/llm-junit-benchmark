from __future__ import annotations

"""Prompt builders for repository generation and test generation."""

import textwrap
from pathlib import Path

from benchmark_pipeline.fs_utils import repo_snapshot, tree_listing


BENCHMARK_DOMAINS: list[str] = [
    "grade-book",
    "recipe-scaler",
    "library-catalog",
    "budget-tracker",
    "payroll-calculator",
    "inventory-manager",
    "weather-analyzer",
    "quiz-engine",
    "fitness-planner",
    "hotel-reservation",
]


def build_repo_prompt(project_name: str | None = None, domain: str | None = None) -> str:
    explicit_name = project_name or "generated-java-app"
    if domain:
        domain_instruction = f"- The application domain MUST be: {domain}."
    else:
        domain_instruction = "- Choose the application domain yourself."
    return textwrap.dedent(
        f"""
        Build a complete, small Maven repository for JDK 21.

        Application domain:
        {domain_instruction}
        - Suggested project name: `{explicit_name}`. Adjust it if a better name matches the chosen domain.

        Structural requirements:
        - Use 6-10 production classes under a coherent domain model.
        - The app should include orchestration logic plus focused helper/domain classes.
        - Include at least one service/orchestrator class that calls methods from at least 3 other classes.
        - Include at least one method that returns different results based on state built from prior method calls.
        - Maven project with `pom.xml`.
        - Java source under `src/main/java`.
        - Include JUnit 5, Maven Surefire, JaCoCo, and Maven Exec plugin config in `pom.xml`, but do not include any tests.
        - Use JaCoCo Maven plugin version `0.8.12` (required for JDK 21 compatibility).
        - Use Maven Surefire plugin version `3.5.2`.
        - JaCoCo should generate XML coverage output during `mvn test`.
        - Configure the Maven Exec plugin so the app can be run with `mvn exec:java`.

        Complexity targets:
        - Total production lines of code (excluding blanks and comments): 300-500.
        - At least 15 public methods across all classes.
        - At least 3 methods with cyclomatic complexity >= 4 (multiple nested if/else, switch cases, or loop + condition combos).
        - Include at least one collection-based workflow (iteration, filtering, aggregation).
        - Include at least one formatter/parser/translator style class and one rule/validation class.
        - Include at least one edge-case-heavy method with 3 or more meaningful scenarios.

        Mutation-testing-friendly patterns (important):
        - Include at least 3 methods with arithmetic or relational operators in non-trivial expressions (e.g., price * quantity - discount, not just getters).
        - Include at least 2 methods with boundary checks (e.g., if (value <= 0), if (list.isEmpty())).
        - Include at least 1 method with a multi-condition boolean expression (e.g., if (a > 0 && b != null && c.contains(x))).
        - Include meaningful branching and validation logic throughout the codebase.
        - Avoid trivial getters/setters that only return or assign a field.
        - Avoid trivial wrappers whose only purpose is to inflate class count.

        Anti-patterns to avoid:
        - Do not use `System.exit()`.
        - Do not use static mutable state (static fields that change at runtime).
        - Do not use `Random` or any non-deterministic source.
        - Do not use deep inheritance hierarchies (max 2 levels).
        - Avoid external services, databases, files, sockets, threads, or frameworks.

        Consistency and compilation:
        - Keep the code understandable enough that another agent can infer expected behavior and write tests.
        - The repository must compile on JDK 21.
        - The repository must pass `mvn test` with zero failing tests.
        - All returned files must be mutually consistent and compile together.
        - Do not reference classes, methods, constructors, fields, or imports that are not defined in the returned repository.
        - Use package names and filenames consistent with the project.
        - Ensure every package declaration matches its file path.
        - Prefer deterministic logic over IO-heavy code.

        Documentation:
        - Include a `README.md` with a short project description.
        - At the end of `README.md`, include a section called "## Complexity Summary" listing: number of classes, total public methods, methods with >= 3 branches, and a one-line description of each class.
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
        - Return ONLY Java test files under `src/test/java`.
        - DO NOT return production files (`src/main/java/...`), `pom.xml`, or `README.md` in the response.
        - Do not modify production code.
        - Assume `pom.xml` already contains JUnit 5 and Surefire.
        - Ensure the test files compile against the provided repository as-is.
        - Do not invent classes, methods, constructors, or fields that do not exist in the repository snapshot.
        - Do not subclass final production classes or override methods unless the production code is explicitly designed for inheritance.
        - Ensure package declarations, imports, and file paths are consistent.
        - Prefer behavior-focused tests, not implementation-detail tests.
        - Cover normal cases, boundary cases, invalid-input cases, and cross-class workflow behavior where applicable.
        - Target meaningful branch coverage, not just method invocation coverage.
        - Add tests that are likely to detect semantic mistakes in formulas, thresholds, validation rules, and formatting.
        - Keep the suite deterministic.
        """
    ).strip()


def build_test_repair_prompt(repo_root: Path, build_output: str) -> str:
    snapshot = repo_snapshot(repo_root, include_extensions={".java", ".xml", ".md"})
    tree = tree_listing(repo_root)
    return textwrap.dedent(
        f"""
        The previously generated JUnit 5 test suite failed to compile or pass `mvn test`.

        Here is the repository tree:
        {tree}

        Here are the repository files (including the failing tests):
        {snapshot}

        Maven/compiler output:
        ```
        {build_output}
        ```

        Return a corrected test suite.

        Requirements:
        - Return ONLY Java test files under `src/test/java` to add/update in the repo.
        - DO NOT return production files (`src/main/java/...`), `pom.xml`, or `README.md` in the response.
        - Return the complete repaired test suite, including unchanged test files.
        - Do not return only the modified file.
        - Fix all compilation errors, import issues, and test failures.
        - Ensure the returned test suite passes `mvn test`.
        - Do not modify production code.
        - Do not invent classes, methods, constructors, or fields that do not exist in the production code.
        - Do not subclass final production classes or override methods unless the production code is explicitly designed for inheritance.
        """
    ).strip()
