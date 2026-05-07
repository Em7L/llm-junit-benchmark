from __future__ import annotations

"""Structured data models used across generation, mutation, and evaluation stages."""

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
    failing_tests: list[str]
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
