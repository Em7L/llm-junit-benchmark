from __future__ import annotations

"""Prompt builders for repository generation and test generation."""

import textwrap
from pathlib import Path

from benchmark_pipeline.fs_utils import repo_snapshot, tree_listing
from benchmark_pipeline.generation.profiles import BenchmarkProfile, render_benchmark_profile_prompt


def build_repo_prompt(project_name: str | None = None, benchmark_profile: BenchmarkProfile | None = None) -> str:
    explicit_name = project_name or "generated-java-app"
    profile = benchmark_profile
    min_classes = profile.min_classes if profile is not None else 6
    max_classes = profile.max_classes if profile is not None else 8
    orchestrator_fanout = 2 if min_classes <= 5 else 3
    if benchmark_profile is not None:
        profile_instruction = render_benchmark_profile_prompt(benchmark_profile)
    else:
        profile_instruction = "- Choose a self-contained application domain and repository complexity yourself."
    return textwrap.dedent(
        f"""
        Build a complete, small Maven repository for JDK 21.

        {profile_instruction}
        - Suggested project name: `{explicit_name}`. Adjust it if a better name matches the chosen domain.

        Structural requirements:
        - Use {min_classes}-{max_classes} production classes under a coherent domain model.
        - The app should include orchestration logic plus focused helper/domain classes.
        - Include at least one service/orchestrator class that calls methods from at least {orchestrator_fanout} other classes.
        - Include at least one method that returns different results based on state built from prior method calls.
        - Maven project with `pom.xml`.
        - Java source under `src/main/java`.
        - Include JUnit 5, Maven Surefire, JaCoCo, and Maven Exec plugin config in `pom.xml`, but do not include any tests.
        - Use JaCoCo Maven plugin version `0.8.12` (required for JDK 21 compatibility).
        - Use Maven Surefire plugin version `3.5.2`.
        - JaCoCo should generate XML coverage output during `mvn test`.
        - Configure the Maven Exec plugin so the app can be run with `mvn exec:java`.

        Code richness requirements:
        - Include at least one collection-based workflow (iteration, filtering, aggregation).
        - Include at least one formatter/parser/translator style class and one rule/validation class.
        - Include at least one edge-case-heavy method with 3 or more meaningful scenarios.
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
        - Avoid external services, databases, files, sockets, threads, or frameworks.

        Consistency and compilation:
        - Keep the code understandable, with clear behavior and explicit rules.
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


def build_repo_repair_prompt(
    repo_root: Path,
    project_name: str | None,
    build_output: str,
    benchmark_profile: BenchmarkProfile | None = None,
) -> str:
    snapshot = repo_snapshot(repo_root, include_extensions={".java", ".xml", ".md"})
    tree = tree_listing(repo_root)
    explicit_name = project_name or "generated-java-app"
    profile_instruction = (
        render_benchmark_profile_prompt(benchmark_profile)
        if benchmark_profile is not None
        else "- Preserve the same overall project idea unless the compiler errors force a structural correction."
    )
    return textwrap.dedent(
        f"""
        The previously generated Maven/JDK21 repository did not compile or pass `mvn test`.

        Suggested project name: `{explicit_name}`.
        {profile_instruction}

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
        - Preserve the same requested complexity level and overall project idea unless the compiler errors force a structural correction.
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
        - Do not return placeholder tests or example-only stubs.
        - Do not use tautological assertions such as `assertTrue(true)`, `assertFalse(false)`, or assertions that only restate literals.
        - Every test method must instantiate production objects, call production methods, or verify exceptions from the production API.
        - Each test file should contain real behavior checks about returned values, state changes, exceptions, or formatted output.

        Bad example:
        ```java
        @Test
        void exampleTest() {{
            assertTrue(true);
        }}
        ```

        Better example:
        ```java
        @Test
        void rejectsInvalidInput() {{
            assertThrows(IllegalArgumentException.class, () -> new SomeProductionType("", 0));
        }}
        ```
        """
    ).strip()


def build_test_repair_prompt(repo_root: Path, build_output: str, *, return_full_suite: bool = True) -> str:
    snapshot = repo_snapshot(repo_root, include_extensions={".java", ".xml", ".md"})
    tree = tree_listing(repo_root)
    repair_return_requirement = (
        "- Return the complete repaired test suite, including unchanged test files.\n"
        "- Do not return only the modified file.\n"
        "- Preserve the full suite and repair weak tests in place rather than dropping files."
        if return_full_suite
        else "- Return only the Java test files that need to be added or updated.\n"
        "- Do not repeat unchanged test files.\n"
        "- Keep every unchanged test file from the existing suite exactly as-is; only return files that must change."
    )
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
        {repair_return_requirement}
        - Fix all compilation errors, import issues, and test failures.
        - Modify only the failing test files identified by the compiler or test output.
        - Do not change unrelated test files unless a closely related shared helper, import, or setup dependency requires it.
        - Ensure the returned test suite passes `mvn test`.
        - Do not modify production code.
        - Do not invent classes, methods, constructors, or fields that do not exist in the production code.
        - Do not subclass final production classes or override methods unless the production code is explicitly designed for inheritance.
        - Replace placeholder tests with real behavior checks against the production API.
        - Do not use tautological assertions such as `assertTrue(true)`, `assertFalse(false)`, or assertions that only restate literals.
        - Every test method must instantiate production objects, call production methods, or verify exceptions from the production API.
        """
    ).strip()
