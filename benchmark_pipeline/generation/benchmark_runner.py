from __future__ import annotations

"""High-level runner for generating test suites with multiple models."""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from benchmark_pipeline.fs_utils import dump_json
from benchmark_pipeline.models import GeneratedTests
from benchmark_pipeline.generation.tests_generation import generate_tests


@dataclass(frozen=True)
class TestBenchmarkConfig:
    repo_dir: Path
    output_dir: Path
    manifest_dir: Path
    models: Sequence[str]


@dataclass(frozen=True)
class TestBenchmarkResult:
    model: str
    output_dir: Path
    manifest_path: Path
    generated_tests: GeneratedTests | None
    error: str | None

    @property
    def passed(self) -> bool:
        return self.error is None


def run_test_generation_benchmark(config: TestBenchmarkConfig) -> list[TestBenchmarkResult]:
    print("-" * 72)
    print("[benchmark] Starting multi-model test generation benchmark")
    print(f"[benchmark] Target models: {', '.join(config.models)}")
    print("-" * 72)

    results: list[TestBenchmarkResult] = []
    for model in config.models:
        results.append(run_model_generation(config, model))

    print("\n" + "=" * 72)
    print("[benchmark] All benchmark runs completed.")
    print("=" * 72)
    return results


def run_model_generation(config: TestBenchmarkConfig, model: str) -> TestBenchmarkResult:
    print(f"\n>>> RUNNING BENCHMARK FOR MODEL: {model} <<<")

    model_output_dir = config.output_dir / model
    model_manifest_path = config.manifest_dir / f"{model}_tests.json"
    model_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        parsed = generate_tests(
            repo_dir=config.repo_dir,
            output_dir=model_output_dir,
            model=model,
        )
    except Exception as exc:
        message = str(exc)
        print(f"[{model}] FAILED: {message}")
        return TestBenchmarkResult(
            model=model,
            output_dir=model_output_dir,
            manifest_path=model_manifest_path,
            generated_tests=None,
            error=message,
        )

    print(f"[{model}] Writing manifest to {model_manifest_path}")
    dump_json(model_manifest_path, parsed.model_dump())
    print(f"[{model}] SUCCESS: Test suite generated in {model_output_dir}")
    return TestBenchmarkResult(
        model=model,
        output_dir=model_output_dir,
        manifest_path=model_manifest_path,
        generated_tests=parsed,
        error=None,
    )
