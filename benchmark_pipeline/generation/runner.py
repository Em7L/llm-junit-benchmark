from __future__ import annotations

"""High-level runners for single baseline and test-suite generation steps."""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from benchmark_pipeline.fs_utils import dump_json
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


@dataclass(frozen=True)
class TestGenerationConfig:
    repo_dir: Path
    output_dir: Path
    model: str
    manifest_path: Path
    max_repairs: int = 2
    initial_output_dir: Path | None = None


def run_baseline_generation(config: BaselineGenerationConfig) -> GeneratedRepo:
    print()
    print("-" * 72)
    print("[baseline] Baseline repository generation")
    print("-" * 72)
    print(f"[baseline] Output directory: {config.output_dir.resolve()}")
    parsed = generate_verified_repo(
        model=config.model,
        project_name=config.project_name,
        output_dir=config.output_dir,
        max_repairs=config.max_repairs,
        verify_cmd=list(config.verify_cmd),
    )
    print(f"[baseline] Writing manifest to {config.manifest_path.resolve()}")
    dump_json(config.manifest_path, parsed.model_dump())
    print()
    print(f"Generated baseline repository at {config.output_dir.resolve()}")
    return parsed


def run_test_generation(config: TestGenerationConfig) -> GeneratedTests:
    parsed = generate_tests(
        repo_dir=config.repo_dir,
        output_dir=config.output_dir,
        model=config.model,
        max_repairs=config.max_repairs,
        initial_output_dir=config.initial_output_dir,
    )
    print(f"[tests] Writing manifest to {config.manifest_path.resolve()}")
    dump_json(config.manifest_path, parsed.model_dump())
    print()
    print(f"Generated test suite at {config.output_dir.resolve()}")
    return parsed
