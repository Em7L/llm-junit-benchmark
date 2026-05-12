from __future__ import annotations

"""Structured data models used across generation and evaluation stages."""

from dataclasses import dataclass

from pydantic import BaseModel, Field


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


@dataclass
class MavenResult:
    label: str
    exit_code: int
    status: str
    status_reason: str | None
    tests: int
    failures: int
    errors: int
    skipped: int
    failing_tests: list[str]
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.status == "passed"


@dataclass
class PitestMutation:
    mutant_id: str
    detected: bool
    status: str
    number_of_tests_run: int
    source_file: str
    mutated_class: str
    mutated_method: str
    method_description: str
    line_number: int | None
    mutator: str
    index: int | None
    block: int | None
    killing_test: str
    description: str


@dataclass
class PitestResult:
    exit_code: int
    report_file: str | None
    total_mutations: int
    status_counts: dict[str, int]
    mutation_score: float | None
    mutations: list[PitestMutation]
    stdout: str
    stderr: str


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
