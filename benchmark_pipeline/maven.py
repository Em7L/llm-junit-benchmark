from __future__ import annotations

"""Maven execution and report-parsing helpers for test and coverage evaluation."""

import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence

from benchmark_pipeline.models import JacocoCoverage, MavenResult


def run_maven_tests(repo_root: Path, maven_cmd: Sequence[str]) -> MavenResult:
    resolved_cmd = resolve_command(maven_cmd)
    completed = subprocess.run(
        resolved_cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    report_dir = repo_root / "target" / "surefire-reports"
    tests, failures, errors, skipped = parse_surefire_reports(report_dir)
    failing_tests = parse_surefire_failing_tests(report_dir)
    return MavenResult(
        label=repo_root.name,
        exit_code=completed.returncode,
        tests=tests,
        failures=failures,
        errors=errors,
        skipped=skipped,
        failing_tests=failing_tests,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_maven_command(repo_root: Path, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    resolved_cmd = resolve_command(command)
    return subprocess.run(
        resolved_cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def resolve_command(command: Sequence[str]) -> list[str]:
    if not command:
        raise ValueError("Command cannot be empty.")

    executable = command[0]
    resolved = shutil.which(executable)

    if resolved is None and sys.platform.startswith("win") and executable.lower() == "mvn":
        resolved = shutil.which("mvn.cmd") or shutil.which("mvn.bat")

    if resolved is None:
        raise FileNotFoundError(
            f"Executable not found: {executable!r}. "
            "If Maven is installed, try passing --maven-cmd mvn.cmd test on Windows."
        )

    return [resolved, *command[1:]]


def parse_surefire_reports(report_dir: Path) -> tuple[int, int, int, int]:
    if not report_dir.exists():
        return (0, 0, 0, 0)

    totals = [0, 0, 0, 0]
    for xml_file in report_dir.glob("TEST-*.xml"):
        root = ET.fromstring(xml_file.read_text(encoding="utf-8"))
        totals[0] += int(root.attrib.get("tests", "0"))
        totals[1] += int(root.attrib.get("failures", "0"))
        totals[2] += int(root.attrib.get("errors", "0"))
        totals[3] += int(root.attrib.get("skipped", "0"))
    return tuple(totals)  # type: ignore[return-value]


def parse_surefire_failing_tests(report_dir: Path) -> list[str]:
    if not report_dir.exists():
        return []

    failing: set[str] = set()
    for xml_file in report_dir.glob("TEST-*.xml"):
        root = ET.fromstring(xml_file.read_text(encoding="utf-8"))
        suite_name = root.attrib.get("name", "")
        for testcase in root.findall("testcase"):
            if testcase.find("failure") is None and testcase.find("error") is None:
                continue
            class_name = testcase.attrib.get("classname") or suite_name
            test_name = testcase.attrib.get("name", "<unknown>")
            failing.add(f"{class_name}#{test_name}")
    return sorted(failing)


def parse_jacoco_report(report_file: Path) -> JacocoCoverage | None:
    if not report_file.exists():
        return None

    report_text = report_file.read_text(encoding="utf-8").strip()
    if not report_text:
        return None

    try:
        root = ET.fromstring(report_text)
    except ET.ParseError:
        return None

    counters: dict[str, dict[str, int]] = {}
    for counter in root.findall("counter"):
        counter_type = counter.attrib["type"]
        counters[counter_type] = {
            "missed": int(counter.attrib.get("missed", "0")),
            "covered": int(counter.attrib.get("covered", "0")),
        }

    return JacocoCoverage(
        instructions_covered=counters.get("INSTRUCTION", {}).get("covered", 0),
        instructions_missed=counters.get("INSTRUCTION", {}).get("missed", 0),
        lines_covered=counters.get("LINE", {}).get("covered", 0),
        lines_missed=counters.get("LINE", {}).get("missed", 0),
        branches_covered=counters.get("BRANCH", {}).get("covered", 0),
        branches_missed=counters.get("BRANCH", {}).get("missed", 0),
    )
