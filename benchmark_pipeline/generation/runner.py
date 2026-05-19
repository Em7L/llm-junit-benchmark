from __future__ import annotations

"""High-level runners for single baseline and test-suite generation steps."""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from benchmark_pipeline.cli_output import heading
from benchmark_pipeline.fs_utils import dump_json
from benchmark_pipeline.generation.profiles import BenchmarkProfile
from benchmark_pipeline.models import GeneratedRepo, GeneratedTests
from benchmark_pipeline.generation.repo_generation import generate_verified_repo
from benchmark_pipeline.generation.tests_generation import generate_tests


@dataclass(frozen=True)
class BaselineGenerationConfig:
    model: str
    project_name: str
    output_dir: Path
    manifest_path: Path
    verify_cmd: Sequence[str]
    max_repairs: int
    benchmark_profile: BenchmarkProfile | None


@dataclass(frozen=True)
class TestGenerationConfig:
    repo_dir: Path
    output_dir: Path
    model: str
    manifest_path: Path
    max_repairs: int = 2
    initial_output_dir: Path | None = None


def run_baseline_generation(config: BaselineGenerationConfig) -> GeneratedRepo:
    heading("[baseline]", "Repository generation")
    parsed = generate_verified_repo(
        model=config.model,
        project_name=config.project_name,
        output_dir=config.output_dir,
        max_repairs=config.max_repairs,
        verify_cmd=list(config.verify_cmd),
        benchmark_profile=config.benchmark_profile,
    )
    dump_json(config.manifest_path, parsed.model_dump())
    print("[baseline] repository ready")
    return parsed


def run_test_generation(config: TestGenerationConfig) -> GeneratedTests:
    parsed = generate_tests(
        repo_dir=config.repo_dir,
        output_dir=config.output_dir,
        model=config.model,
        max_repairs=config.max_repairs,
        initial_output_dir=config.initial_output_dir,
    )
    dump_json(config.manifest_path, parsed.model_dump())
    print(f"[tests: {config.model}] suite ready")
    return parsed
