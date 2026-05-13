# LLM JUnit Benchmark Pipeline

This project is a Python pipeline for generating small Java/Maven repositories, generating JUnit 5 test suites for them with LLMs, and evaluating the generated tests with Maven, JaCoCo, and PIT mutation testing.

The numbered Python files are CLI entrypoints. The implementation lives in the `benchmark_pipeline/` package.

## Prerequisites

- Python 3.10+
- Maven on `PATH`
- JDK 21 on `PATH`
- An API key for the model provider you use
- Network access for LLM API calls and Maven dependency downloads

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Environment

Create a `.env` file in the project root. Do not commit this file.

```env
OPENAI_API_KEY=your_openai_api_key_here

# Optional defaults
REPO_GEN_MODEL=gpt-5.4-mini
TEST_GEN_MODEL=gpt-4o

# Optional DeepSeek support
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

Model provider selection is currently simple: model names containing `deepseek` use the DeepSeek API key and base URL; all other model names use OpenAI.

## Run The Full Pipeline

Run the complete workflow with the default models from `.env` or `benchmark_pipeline/config.py`:

```powershell
python 0_run_pipeline.py
```

Run with explicit models:

```powershell
python 0_run_pipeline.py --repo-model gpt-5.4-mini --tests-model gpt-4o
```

The full pipeline does the following:

1. Generates one baseline Java 21 Maven repository.
2. Validates the generated repository structure.
3. Runs Maven to verify that the baseline repository builds.
4. Attempts to repair the baseline repository up to `--max-repairs` times if needed.
5. Generates a JUnit 5 test suite for the verified baseline repository.
6. Runs the generated tests against the baseline.
7. Disables generated test methods that fail against the baseline, because the baseline is treated as the reference implementation for the experiment.
8. Runs JaCoCo coverage and PIT mutation testing on the cleaned test suite.
9. Writes JSON, Markdown, and PIT reports under `artifacts/reports`.

## Run Individual Steps

Generate only the baseline repository:

```powershell
python 1_generate_baseline_repo.py --model gpt-5.4-mini
```

Generate tests for an existing baseline repository:

```powershell
python 2_generate_tests.py --model gpt-4o
```

Evaluate generated tests with Maven, JaCoCo, and PIT:

```powershell
python 3_evaluate_with_pitest.py
```

The default paths are:

- Baseline repository: `artifacts/baseline_repo`
- Generated tests: `artifacts/generated_tests`
- Reports: `artifacts/reports`

## Benchmark Multiple Test Models

After generating a baseline repository, generate separate test suites for multiple models:

```powershell
python 2b_benchmark_tests.py
```

This uses `TEST_MODELS_LIST` from `benchmark_pipeline/config.py` and writes one generated test suite per model under:

```text
artifacts/benchmarks/<model-name>/
```

Then evaluate all benchmark suites:

```powershell
python 3_evaluate_with_pitest.py --tests-dir artifacts/benchmarks
```

This compares the generated suites against the same baseline repository under the same evaluation procedure.

## Outputs

The main generated files and folders are:

- `artifacts/baseline_repo/`: generated Java Maven repository
- `artifacts/generated_tests/`: generated JUnit 5 tests for the default single-suite workflow
- `artifacts/benchmarks/`: generated test suites for the multi-model benchmark workflow
- `artifacts/manifests/`: structured LLM responses saved as JSON
- `artifacts/reports/evaluation_report.json`: machine-readable evaluation report
- `artifacts/reports/evaluation_report.md`: human-readable evaluation report
- `artifacts/reports/pit-reports/`: copied PIT XML/HTML reports

Temporary staged repositories are created under `artifacts/.staging/` during evaluation and can be deleted after a run.

## Evaluation Behavior

The baseline repository is treated as the correct reference implementation for one experiment iteration. If generated tests fail against the baseline, those test methods are considered faulty for this experiment and are disabled in the staged evaluation copy before mutation testing.

If generated test sources do not compile, the suite cannot be cleaned method-by-method, so PIT is skipped for that suite.

PIT is used for mutation testing. It mutates the production code and checks whether the generated tests detect those behavioral changes. JaCoCo is used separately for line and branch coverage.

## Useful Commands

Run the Python test suite:

```powershell
python -m unittest discover -s tests
```

Run Ruff:

```powershell
python -m ruff check .
```

Compile-check the Python files:

```powershell
python -m compileall 0_run_pipeline.py 1_generate_baseline_repo.py 2_generate_tests.py 2b_benchmark_tests.py 3_evaluate_with_pitest.py benchmark_pipeline tests
```

## Notes

- The pipeline is intended for controlled empirical experiments, not production Java project generation.
- The generated baseline code is assumed correct only within one experiment iteration.
- Results should be interpreted for the selected models, prompts, generated repositories, and evaluation setup.
- Do not commit `.env`, API keys, or confidential thesis drafts.
