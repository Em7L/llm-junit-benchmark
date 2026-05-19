# LLM JUnit Benchmark Pipeline

This project is a Python pipeline for generating small Java/Maven repositories, generating JUnit 5 test suites for them with LLMs, and evaluating the generated tests with Maven, JaCoCo, and PIT mutation testing.

The main single-run CLI entrypoint is `run_pipeline.py`. The intended multi-run experiment entrypoint is `run_experiment_matrix.py`. The implementation lives in the `benchmark_pipeline/` package.

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

Run the complete workflow with the default models from `.env` or `benchmark_pipeline/config.py` and an explicit benchmark profile:

```powershell
python run_pipeline.py --profile-id low
```

By default, each full pipeline run is preserved under a new run directory:

```text
artifacts/runs/profile-<profile-id>__repo-<repo-model>__tests-<test-models>/run-001/
artifacts/runs/profile-<profile-id>__repo-<repo-model>__tests-<test-models>/run-002/
```

Run with explicit models:

```powershell
python run_pipeline.py --profile-id low --repo-model gpt-5.4-mini --tests-model gpt-4o
```

Run the intended model-comparison workflow with one baseline generator and multiple test-suite generators:

```powershell
python run_pipeline.py --profile-id high --repo-model gpt-5.4-mini --tests-models gpt-4o gpt-5.4-mini gpt-4o-mini
```

The benchmark profile determines the structural complexity target for baseline repository generation. The model still chooses the concrete application domain, but it must satisfy the selected complexity frame. Profiles are defined centrally in [benchmark_pipeline/generation/profiles.py](benchmark_pipeline/generation/profiles.py). The current benchmark frame contains `2` fixed profiles:

- `low`
- `high`

The full pipeline does the following:

1. Resolves one predefined complexity profile.
2. Generates one baseline Java 21 Maven repository for that complexity target.
3. Validates the generated repository structure.
4. Runs Maven to verify that the baseline repository builds.
5. Attempts to repair the baseline repository up to `--max-repairs` times if needed.
6. Generates one JUnit 5 test suite per test model for the same verified baseline repository.
7. Runs each generated test suite against the same baseline.
8. If a generated test suite fails semantic validation, it is repaired as a complete suite.
9. If a generated test suite compiles or verifies poorly, verification-time repair may return only the changed test files; those updates are merged into the previously generated suite before re-verification.
10. Disables generated test methods that fail against the baseline, because the baseline is treated as the reference implementation for the experiment.
11. Runs JaCoCo coverage and PIT mutation testing on each cleaned test suite.
12. Writes comparison JSON/Markdown reports and copied PIT reports under the run directory.

## Compare Multiple Test Models

Use `run_pipeline.py --profile-id ... --tests-models ...` when you want one preserved comparison run. The pipeline generates one baseline repository and then creates one generated test suite per test model under:

```text
artifacts/runs/<model-combination>/run-N/generated_tests/_final_selected/<model-name>/
```

Evaluation then compares all generated suites against the same baseline repository under the same Maven, JaCoCo, and PIT procedure.

## Run The Full Experiment Matrix

Use `run_experiment_matrix.py` for the intended thesis experiment workflow across profiles, baseline-generation models, and preserved repetitions.

Run the default matrix:

```powershell
python run_experiment_matrix.py
```

Default matrix settings:

- profiles: `low`, `high`
- repository-generation models: `gpt-5.4-mini`, `deepseek-v4-flash`
- test-generation models for every run: `gpt-5.4-mini`, `deepseek-v4-flash`, `gemini-3-flash-preview`, `gpt-4o-mini`
- target repetitions per condition: `8`

This produces the 4 default conditions:

- `low` + `gpt-5.4-mini`
- `high` + `gpt-5.4-mini`
- `low` + `deepseek-v4-flash`
- `high` + `deepseek-v4-flash`

Useful variants:

```powershell
python run_experiment_matrix.py --dry-run
python run_experiment_matrix.py --profile-ids low --repo-models gpt-5.4-mini
python run_experiment_matrix.py --repetitions 8 --continue-on-error
```

Matrix runner behavior:

- Existing preserved `run-*` directories are used to infer progress for each condition.
- The runner only executes the missing runs needed to reach the target repetition count.
- `--dry-run` prints the plan without executing pipeline runs.
- A timing summary is written to `artifacts/runs/experiment_timing_summary.json` by default.
- If a provider quota / credit / rate-limit failure is detected during a run, that current `run-*` directory is deleted and the script stops immediately.

Operational note:

- If you manually interrupt the matrix runner during a run, delete that latest partial `run-*` directory before restarting. The runner currently infers progress from existing run directories.

To aggregate many preserved `comparison_report.json` files into one study-level summary, run:

```powershell
python summarize_comparison_reports.py
```

By default this scans `artifacts/runs/` and writes:

- `artifacts/summary/comparison_reports_summary.json`
- `artifacts/summary/comparison_reports_summary.md`

## Outputs

The main generated files and folders are:

- `artifacts/runs/<model-combination>/run-N/baseline_repo/`: generated Java Maven repository
- `artifacts/runs/<model-combination>/run-N/generated_tests/_final_selected/<model-name>/`: final selected generated JUnit 5 test suite used for evaluation
- `artifacts/runs/<model-combination>/run-N/generated_tests/_initial_snapshot/<model-name>/`: preserved initial pre-repair test-suite snapshot when repair is attempted
- `artifacts/runs/<model-combination>/run-N/manifests/`: structured LLM responses saved as JSON
- `artifacts/runs/<model-combination>/run-N/manifests/benchmark_profile.json`: selected benchmark profile for the run
- `artifacts/runs/<model-combination>/run-N/reports/comparison_report.json`: machine-readable comparison report
- `artifacts/runs/<model-combination>/run-N/reports/comparison_report.md`: Markdown comparison table rendered from the comparison JSON payload
- `artifacts/runs/<model-combination>/run-N/reports/pit-reports/_final_selected/<model-name>/`: copied PIT XML/HTML reports for final evaluated suites
- `artifacts/runs/<model-combination>/run-N/reports/pit-reports/_initial_snapshot/<model-name>/`: copied PIT XML/HTML reports for initial suite snapshots
- `artifacts/runs/experiment_timing_summary.json`: timing summary for the latest `run_experiment_matrix.py` invocation

Temporary staged repositories are created under each run directory's `.staging/` folder during evaluation and can be deleted after a run.

## Evaluation Behavior

The baseline repository is treated as the correct reference implementation for one experiment iteration. If generated tests fail against the baseline, those test methods are considered faulty for this experiment and are disabled in the staged evaluation copy before mutation testing.

If generated test sources do not compile, the suite cannot be cleaned method-by-method, so PIT is skipped for that suite.

PIT is used for mutation testing. It mutates the production code and checks whether the generated tests detect those behavioral changes. JaCoCo is used separately for line and branch coverage.

Comparison and summary reports are written as both JSON and Markdown. The JSON files are the canonical records; the Markdown files are human-readable views rendered from those same payloads.

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
python -m compileall run_pipeline.py run_experiment_matrix.py summarize_comparison_reports.py benchmark_pipeline tests
```

## Notes

- The pipeline is intended for controlled empirical experiments, not production Java project generation.
- The generated baseline code is assumed correct only within one experiment iteration.
- Results should be interpreted for the selected models, prompts, generated repositories, and evaluation setup.
- Do not commit `.env`, API keys, or confidential thesis drafts.
