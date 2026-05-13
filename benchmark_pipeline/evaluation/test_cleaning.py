from __future__ import annotations

"""Utilities for quarantining generated tests that fail on the baseline."""

import re
from pathlib import Path


DISABLED_ANNOTATION = '@Disabled("Excluded because it fails on the baseline")'
DISABLED_IMPORT = "import org.junit.jupiter.api.Disabled;"
JUNIT_WILDCARD_IMPORT = "import org.junit.jupiter.api.*;"


def disable_baseline_failing_tests(repo_root: Path, failing_tests: list[str]) -> list[str]:
    """Disable failing JUnit methods in the staged repository copy.

    The source generated tests are not changed. This only edits the staged copy used
    for coverage and PIT, so mutation scoring is based on tests that first pass the
    reference implementation.
    """
    grouped = group_failing_tests_by_file(repo_root, failing_tests)
    expected = sorted(test_id for test_ids in grouped.values() for test_id in test_ids)
    disabled: list[str] = []

    for source_file, test_ids in grouped.items():
        methods = [test_id.split("#", 1)[1] for test_id in test_ids]
        disabled_methods = disable_methods_in_file(source_file, methods)
        disabled.extend(
            test_id
            for test_id in test_ids
            if normalize_test_method_name(test_id.split("#", 1)[1]) in disabled_methods
        )

    missing = sorted(set(expected) - set(disabled))
    if missing:
        raise RuntimeError(
            "Could not disable all baseline-failing generated tests: "
            + ", ".join(missing)
        )

    return sorted(disabled)


def group_failing_tests_by_file(repo_root: Path, failing_tests: list[str]) -> dict[Path, list[str]]:
    grouped: dict[Path, list[str]] = {}
    for test_id in failing_tests:
        if "#" not in test_id:
            continue

        class_name, raw_method_name = test_id.split("#", 1)
        method_name = normalize_test_method_name(raw_method_name)
        if not class_name or not method_name or method_name == "<unknown>":
            continue

        top_level_class = class_name.split("$", 1)[0]
        source_file = repo_root / "src" / "test" / "java" / Path(*top_level_class.split(".")).with_suffix(".java")
        grouped.setdefault(source_file, []).append(f"{class_name}#{method_name}")

    return grouped


def normalize_test_method_name(method_name: str) -> str:
    return re.split(r"[\[(]", method_name, maxsplit=1)[0].strip()


def disable_methods_in_file(source_file: Path, method_names: list[str]) -> set[str]:
    if not source_file.exists():
        return set()

    lines = source_file.read_text(encoding="utf-8").splitlines(keepends=True)
    disabled: set[str] = set()

    for method_name in sorted({normalize_test_method_name(name) for name in method_names}):
        method_line = find_method_declaration_line(lines, method_name)
        if method_line is None or method_already_disabled(lines, method_line):
            if method_line is not None:
                disabled.add(method_name)
            continue

        indent = re.match(r"^(\s*)", lines[method_line]).group(1)  # type: ignore[union-attr]
        newline = "\r\n" if lines[method_line].endswith("\r\n") else "\n"
        lines.insert(method_line, f"{indent}{DISABLED_ANNOTATION}{newline}")
        disabled.add(method_name)

    if disabled:
        lines = ensure_disabled_import(lines)
        source_file.write_text("".join(lines), encoding="utf-8")

    return disabled


def find_method_declaration_line(lines: list[str], method_name: str) -> int | None:
    pattern = re.compile(
        rf"^\s*(?:public|protected|private)?\s*(?:final\s+)?"
        rf"(?:void|[\w<>\[\], ?]+)\s+{re.escape(method_name)}\s*\("
    )
    for index, line in enumerate(lines):
        if pattern.search(line):
            return index
    return None


def method_already_disabled(lines: list[str], method_line: int) -> bool:
    index = method_line - 1
    while index >= 0 and (not lines[index].strip() or lines[index].lstrip().startswith("@")):
        if lines[index].strip().startswith("@Disabled"):
            return True
        index -= 1
    return False


def ensure_disabled_import(lines: list[str]) -> list[str]:
    if any(DISABLED_IMPORT in line or JUNIT_WILDCARD_IMPORT in line for line in lines):
        return lines

    newline = detect_newline(lines)
    import_indexes = [index for index, line in enumerate(lines) if line.startswith("import ")]
    if import_indexes:
        lines.insert(import_indexes[-1] + 1, f"{DISABLED_IMPORT}{newline}")
        return lines

    package_indexes = [index for index, line in enumerate(lines) if line.startswith("package ")]
    if package_indexes:
        lines.insert(package_indexes[0] + 1, newline)
        lines.insert(package_indexes[0] + 2, f"{DISABLED_IMPORT}{newline}")
        return lines

    lines.insert(0, f"{DISABLED_IMPORT}{newline}")
    return lines


def detect_newline(lines: list[str]) -> str:
    for line in lines:
        if line.endswith("\r\n"):
            return "\r\n"
    return "\n"
