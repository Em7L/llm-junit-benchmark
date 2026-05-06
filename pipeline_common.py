from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")


class FileArtifact(BaseModel):
    path: str = Field(description="Repository-relative file path using forward slashes.")
    content: str = Field(description="Complete file content.")


class GeneratedRepo(BaseModel):
    project_name: str
    description: str
    files: list[FileArtifact]


class GeneratedTests(BaseModel):
    summary: str
    files: list[FileArtifact]
    assumptions: list[str] = Field(default_factory=list)


class Mutant(BaseModel):
    mutant_id: str
    description: str
    changed_files: list[FileArtifact]


class GeneratedMutants(BaseModel):
    source_project_name: str
    summary: str
    mutants: list[Mutant]


@dataclass
class MavenResult:
    label: str
    exit_code: int
    tests: int
    failures: int
    errors: int
    skipped: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and self.failures == 0 and self.errors == 0


@dataclass
class JacocoCoverage:
    instructions_covered: int
    instructions_missed: int
    lines_covered: int
    lines_missed: int
    branches_covered: int
    branches_missed: int

    @property
    def instruction_rate(self) -> float:
        total = self.instructions_covered + self.instructions_missed
        return self.instructions_covered / total if total else 0.0

    @property
    def line_rate(self) -> float:
        total = self.lines_covered + self.lines_missed
        return self.lines_covered / total if total else 0.0

    @property
    def branch_rate(self) -> float:
        total = self.branches_covered + self.branches_missed
        return self.branches_covered / total if total else 0.0


def get_client() -> OpenAI:
    return OpenAI()


def safe_rel_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/").strip("/")
    candidate = Path(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe relative path: {raw_path!r}")
    return candidate


def write_artifacts(root: Path, files: Sequence[FileArtifact]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for artifact in files:
        target = root / safe_rel_path(artifact.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(artifact.content, encoding="utf-8")


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def repo_snapshot(
    root: Path,
    *,
    include_extensions: Iterable[str] | None = None,
    ignore_dirs: Iterable[str] = ("target", ".git", ".idea", ".vscode", "__pycache__"),
) -> str:
    include_set = {ext.lower() for ext in include_extensions or []}
    ignore_set = set(ignore_dirs)
    chunks: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in ignore_set for part in path.parts):
            continue
        if include_set and path.suffix.lower() not in include_set and path.name != "pom.xml":
            continue
        rel = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8")
        chunks.append(f"FILE: {rel}\n```\n{content}\n```")

    return "\n\n".join(chunks)


def tree_listing(root: Path, ignore_dirs: Iterable[str] = ("target", ".git")) -> str:
    ignore_set = set(ignore_dirs)
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if any(part in ignore_set for part in path.parts):
            continue
        rel = path.relative_to(root)
        suffix = "/" if path.is_dir() else ""
        lines.append(rel.as_posix() + suffix)
    return "\n".join(lines)


def parse_response(model: str, schema: type[BaseModel], instructions: str, user_input: str) -> BaseModel:
    client = get_client()
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_input},
        ],
        text_format=schema,
    )
    if response.output_parsed is None:
        raise RuntimeError("Model did not return structured output.")
    return response.output_parsed


def copy_into(source_root: Path, destination_root: Path) -> None:
    for path in sorted(source_root.rglob("*")):
        rel = path.relative_to(source_root)
        target = destination_root / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


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
    tests, failures, errors, skipped = parse_surefire_reports(repo_root / "target" / "surefire-reports")
    return MavenResult(
        label=repo_root.name,
        exit_code=completed.returncode,
        tests=tests,
        failures=failures,
        errors=errors,
        skipped=skipped,
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


def stage_repo_with_tests(repo_root: Path, tests_root: Path) -> Path:
    staging_root = repo_root.parent / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    temp_dir = staging_root / f"agent-eval-{uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    copy_into(repo_root, temp_dir)
    copy_into(tests_root, temp_dir)
    return temp_dir


def dump_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def markdown_report(
    baseline_result: MavenResult,
    baseline_coverage: JacocoCoverage | None,
    mutant_results: list[dict[str, object]],
    mutation_score: float,
) -> str:
    lines = [
        "# Mutation Evaluation Report",
        "",
        "## Baseline Repository",
        f"- Passed: `{baseline_result.passed}`",
        f"- Exit code: `{baseline_result.exit_code}`",
        f"- Tests: `{baseline_result.tests}`",
        f"- Failures: `{baseline_result.failures}`",
        f"- Errors: `{baseline_result.errors}`",
        f"- Skipped: `{baseline_result.skipped}`",
        "",
        "## Coverage",
    ]
    if baseline_coverage is None:
        lines.append("- JaCoCo report not found.")
    else:
        lines.extend(
            [
                f"- Instruction coverage: `{baseline_coverage.instruction_rate:.2%}`",
                f"- Line coverage: `{baseline_coverage.line_rate:.2%}`",
                f"- Branch coverage: `{baseline_coverage.branch_rate:.2%}`",
            ]
        )
    lines.extend(
        [
            "",
        "## Mutants",
        ]
    )
    for result in mutant_results:
        lines.extend(
            [
                f"- `{result['mutant_id']}`: killed=`{result['killed']}` exit_code=`{result['exit_code']}` failures=`{result['failures']}` errors=`{result['errors']}`",
                f"  description: {result['description']}",
            ]
        )
    lines.extend(
        [
            "",
            "## Summary",
            f"- Mutation score: `{mutation_score:.2%}`",
            f"- Mutants killed: `{sum(1 for item in mutant_results if item['killed'])}/{len(mutant_results)}`",
        ]
    )
    return "\n".join(lines)


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
        - Use package names and filenames consistent with the project.
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
        - Prefer behavior-focused tests, not implementation-detail tests.
        - Cover normal cases, boundary cases, invalid-input cases, and cross-class workflow behavior where applicable.
        - Target meaningful branch coverage, not just method invocation coverage.
        - Add tests that are likely to detect semantic mistakes in formulas, thresholds, validation rules, and formatting.
        - Keep the suite deterministic.
        """
    ).strip()


def build_mutation_prompt(repo_root: Path, mutant_count: int) -> str:
    snapshot = repo_snapshot(repo_root, include_extensions={".java", ".xml", ".md"})
    tree = tree_listing(repo_root)
    return textwrap.dedent(
        f"""
        Here is the repository tree:
        {tree}

        Here are the repository files:
        {snapshot}

        Generate {mutant_count} single-bug mutants for this Maven/JDK21 project.

        Requirements:
        - Each mutant should introduce exactly one realistic bug.
        - Each mutant should change as few files as possible.
        - Return full replacement content only for the changed files of each mutant.
        - Prefer semantic bugs: off-by-one, wrong operator, missing validation, incorrect branch, bad formula.
        - Prefer mutants that change observable behavior for common inputs.
        - Avoid equivalent or likely-equivalent mutants.
        - Do not swap operands in commutative expressions unless another semantic change makes behavior observably different.
        - Do not make formatting-only, naming-only, or refactoring-only changes.
        - Do not generate mutants whose behavior is identical for the obvious valid and invalid inputs a test suite should try.
        - Do not break the Maven layout or package names.
        - Make the mutants compile if possible.
        """
    ).strip()


def as_serializable_maven_result(result: MavenResult) -> dict[str, object]:
    return asdict(result)


def as_serializable_coverage(coverage: JacocoCoverage | None) -> dict[str, object] | None:
    if coverage is None:
        return None

    payload = asdict(coverage)
    payload["instruction_rate"] = coverage.instruction_rate
    payload["line_rate"] = coverage.line_rate
    payload["branch_rate"] = coverage.branch_rate
    return payload
