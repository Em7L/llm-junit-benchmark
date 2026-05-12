from __future__ import annotations

"""CLI entrypoint for benchmarking multiple GPT models for test generation."""

from pathlib import Path
from benchmark_pipeline.config import TEST_MODELS_LIST
from benchmark_pipeline.fs_utils import dump_json
from benchmark_pipeline.tests_generation import generate_tests

def main() -> None:
    repo_dir = Path("artifacts/baseline_repo")
    base_output_dir = Path("artifacts/benchmarks")
    base_manifest_dir = Path("artifacts/manifests/benchmarks")

    print("-" * 72)
    print("[benchmark] Starting multi-model test generation benchmark")
    print(f"[benchmark] Target models: {', '.join(TEST_MODELS_LIST)}")
    print("-" * 72)

    for model in TEST_MODELS_LIST:
        print(f"\n>>> RUNNING BENCHMARK FOR MODEL: {model} <<<")
        
        # Create model-specific paths
        model_output_dir = base_output_dir / model
        model_manifest_path = base_manifest_dir / f"{model}_tests.json"
        
        # Ensure directories exist
        model_manifest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            parsed = generate_tests(
                repo_dir=repo_dir,
                output_dir=model_output_dir,
                model=model,
            )
            
            print(f"[{model}] Writing manifest to {model_manifest_path}")
            dump_json(model_manifest_path, parsed.model_dump())
            print(f"[{model}] SUCCESS: Test suite generated in {model_output_dir}")
            
        except Exception as e:
            print(f"[{model}] FAILED: {str(e)}")

    print("\n" + "=" * 72)
    print("[benchmark] All benchmark runs completed.")
    print("=" * 72)

if __name__ == "__main__":
    main()
