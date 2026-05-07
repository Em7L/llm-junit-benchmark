# AI Mutation Testing Pipeline

This folder contains four Python scripts that orchestrate a small mutation-testing workflow driven by three separate OpenAI agent prompts.
The shared implementation now lives in the `benchmark_pipeline/` package, while the numbered scripts remain thin CLI entrypoints.

## Scripts

1. `1_generate_baseline_repo.py`
   Generates a moderately complex Maven/JDK 21 Java repository with production code only.
2. `2_generate_tests.py`
   Generates a JUnit 5 test suite for the baseline repository from step 1.
3. `3_generate_mutants.py`
   Generates multiple single-bug mutant repositories from the baseline repository.
4. `4_evaluate_mutants.py`
   Runs Agent 2's tests against the baseline repository and each mutant, then writes a report with mutation results and JaCoCo coverage from the baseline run.

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
python 1_generate_baseline_repo.py
python 2_generate_tests.py
python 3_generate_mutants.py --count 5
python 4_evaluate_mutants.py
```

## Outputs

- `artifacts/baseline_repo`
- `artifacts/generated_tests`
- `artifacts/mutants`
- `artifacts/manifests/*.json`
- `artifacts/reports/evaluation_report.json`
- `artifacts/reports/evaluation_report.md`

## Notes

- The implementation uses the OpenAI Responses API with structured outputs.
- The evaluation uses multiple single-bug mutants because that gives you a mutation score, which is more informative than a single pass/fail result against one buggy repository.
- Agent 1 is prompted to include JaCoCo XML coverage reporting in the generated Maven project.
- Agent 1 is now prompted to generate a richer domain app with 6-10 production classes, branching, validation, and collection-based workflow logic.
- Agent 3 is now prompted to avoid likely-equivalent mutants and prefer observable semantic bugs.
