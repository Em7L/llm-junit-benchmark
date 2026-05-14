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

By default, each full pipeline run is preserved under a new run directory:

```text
artifacts/runs/repo-<repo-model>__tests-<test-models>/run-001/
artifacts/runs/repo-<repo-model>__tests-<test-models>/run-002/
```

Run with explicit models:

```powershell
python 0_run_pipeline.py --repo-model gpt-5.4-mini --tests-model gpt-4o
```

Run the intended model-comparison workflow with one baseline generator and multiple test-suite generators:

```powershell
python 0_run_pipeline.py --repo-model gpt-5.4-mini --tests-models gpt-4o gpt-5.4-mini gpt-4o-mini
```

The full pipeline does the following:

1. Generates one baseline Java 21 Maven repository.
2. Validates the generated repository structure.
3. Runs Maven to verify that the baseline repository builds.
4. Attempts to repair the baseline repository up to `--max-repairs` times if needed.
5. Generates one JUnit 5 test suite per test model for the same verified baseline repository.
6. Runs each generated test suite against the same baseline.
7. Disables generated test methods that fail against the baseline, because the baseline is treated as the reference implementation for the experiment.
8. Runs JaCoCo coverage and PIT mutation testing on each cleaned test suite.
9. Writes comparison JSON/Markdown reports and copied PIT reports under `artifacts/reports`.

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

This standalone evaluation step writes only the comparison report plus copied PIT reports.

The default paths are:

- Baseline repository: `artifacts/baseline_repo`
- Generated tests: `artifacts/generated_tests`
- Reports: `artifacts/reports`

## Compare Multiple Test Models

Use `0_run_pipeline.py --tests-models ...` for the main experiment. The pipeline generates one baseline repository and then creates one generated test suite per test model under:

```text
artifacts/generated_tests/<model-name>/
```

Evaluation then compares all generated suites against the same baseline repository under the same Maven, JaCoCo, and PIT procedure.

## Outputs

The main generated files and folders are:

- `artifacts/runs/<model-combination>/run-N/baseline_repo/`: generated Java Maven repository
- `artifacts/runs/<model-combination>/run-N/generated_tests/<model-name>/`: generated JUnit 5 tests for each test model
- `artifacts/runs/<model-combination>/run-N/manifests/`: structured LLM responses saved as JSON
- `artifacts/runs/<model-combination>/run-N/reports/comparison_report.json`: machine-readable comparison report
- `artifacts/runs/<model-combination>/run-N/reports/comparison_report.md`: Markdown comparison table across test models
- `artifacts/runs/<model-combination>/run-N/reports/pit-reports/`: copied PIT XML/HTML reports

Temporary staged repositories are created under each run directory's `.staging/` folder during evaluation and can be deleted after a run.

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
python -m compileall 0_run_pipeline.py 1_generate_baseline_repo.py 2_generate_tests.py 3_evaluate_with_pitest.py benchmark_pipeline tests
```

## Notes

- The pipeline is intended for controlled empirical experiments, not production Java project generation.
- The generated baseline code is assumed correct only within one experiment iteration.
- Results should be interpreted for the selected models, prompts, generated repositories, and evaluation setup.
- Do not commit `.env`, API keys, or confidential thesis drafts.
