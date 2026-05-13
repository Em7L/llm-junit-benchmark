from __future__ import annotations

"""CLI entrypoint for benchmarking multiple GPT models for test generation."""

from pathlib import Path

from benchmark_pipeline.config import TEST_MODELS_LIST
from benchmark_pipeline.generation.benchmark_runner import TestBenchmarkConfig, run_test_generation_benchmark

def main() -> None:
    run_test_generation_benchmark(
        TestBenchmarkConfig(
            repo_dir=Path("artifacts/baseline_repo"),
            output_dir=Path("artifacts/benchmarks"),
            manifest_dir=Path("artifacts/manifests/benchmarks"),
            models=TEST_MODELS_LIST,
        )
    )

if __name__ == "__main__":
    main()
