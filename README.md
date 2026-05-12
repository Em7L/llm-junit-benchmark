# AI Mutation Testing Pipeline

This folder contains Python scripts that orchestrate a small mutation-testing workflow driven by OpenAI agent prompts and PIT.
The shared implementation now lives in the `benchmark_pipeline/` package, while the numbered scripts remain thin CLI entrypoints.

## Scripts

1. `1_generate_baseline_repo.py`
   Generates a moderately complex Maven/JDK 21 Java repository with production code only.
2. `2_generate_tests.py`
   Generates a JUnit 5 test suite for the baseline repository from step 1.
3. `3_evaluate_with_pitest.py`
   Runs Agent 2's tests against the baseline repository, then writes a report with JaCoCo coverage and PIT mutation results.

## Expected local prerequisites

- Python 3.10+
- Maven on `PATH`
- JDK 21 on `PATH`
- `OPENAI_API_KEY` set either in the environment or in `.env`

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## `.env`

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-5.4-mini
```

## Run

```powershell
python 0_run_pipeline.py
```

Or run each stage separately:

```powershell
python 1_generate_baseline_repo.py
python 2_generate_tests.py
python 3_evaluate_with_pitest.py
```

## Outputs

- `artifacts/baseline_repo`
- `artifacts/generated_tests`
- `artifacts/manifests/*.json`
- `artifacts/reports/evaluation_report.json`
- `artifacts/reports/evaluation_report.md`

## Notes

- The implementation uses the OpenAI Responses API with structured outputs.
- The evaluation uses PIT mutation testing instead of AI-generated mutant repositories.
- PIT is configured in the staged evaluation repository with pinned Maven plugin versions and XML/HTML report output.
- Agent 1 is prompted to include JaCoCo XML coverage reporting in the generated Maven project.
- Agent 1 is now prompted to generate a richer domain app with 6-10 production classes, branching, validation, and collection-based workflow logic.
