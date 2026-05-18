# Benchmark Profile Commands

This file records the planned manual command matrix for the thesis experiment.

## Experiment Design

- Repository-generation models:
  - `gpt-5.4-mini`
  - `deepseek-v4-flash`
- Test-generation models:
  - `gpt-5.4-mini`
  - `deepseek-v4-flash`
  - `gemini-3-flash-preview`
  - `gpt-4o-mini`
- Complexity levels:
  - `low`
  - `high`
- Repetitions:
  - `8` runs for each repository-generation model and complexity level

Totals:

- `2` repository-generation models × `2` complexity levels × `8` runs = `32` repositories
- `32` repositories × `4` test-generation models = `128` generated test suites

## Fixed Test-Generation Set

Use the same test-generation model set in every run:

```powershell
--tests-models gpt-5.4-mini deepseek-v4-flash gemini-3-flash-preview gpt-4o-mini
```

## Command Matrix

Run each of the following commands `8` times:

### Low / GPT Repo Generator

```powershell
python run_pipeline.py --profile-id low --repo-model gpt-5.4-mini --tests-models gpt-5.4-mini deepseek-v4-flash gemini-3-flash-preview gpt-4o-mini
```

### High / GPT Repo Generator

```powershell
python run_pipeline.py --profile-id high --repo-model gpt-5.4-mini --tests-models gpt-5.4-mini deepseek-v4-flash gemini-3-flash-preview gpt-4o-mini
```

### Low / DeepSeek Repo Generator

```powershell
python run_pipeline.py --profile-id low --repo-model deepseek-v4-flash --tests-models gpt-5.4-mini deepseek-v4-flash gemini-3-flash-preview gpt-4o-mini
```

### High / DeepSeek Repo Generator

```powershell
python run_pipeline.py --profile-id high --repo-model deepseek-v4-flash --tests-models gpt-5.4-mini deepseek-v4-flash gemini-3-flash-preview gpt-4o-mini
```

## Tracking Plan

Complete `8` preserved runs for each condition:

- `gpt-5.4-mini` repo generator / `low`
- `gpt-5.4-mini` repo generator / `high`
- `deepseek-v4-flash` repo generator / `low`
- `deepseek-v4-flash` repo generator / `high`
