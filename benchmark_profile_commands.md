# Benchmark Profile Commands

This file lists the `2` benchmark-profile commands derived from the current complexity-based benchmark frame.

Use this command template:

```powershell
python 0_run_pipeline.py --profile-id <profile-id> --repo-model <repo-model> --tests-models <test-model-1> <test-model-2>
```

Example with concrete models:

```powershell
python 0_run_pipeline.py --profile-id low --repo-model gpt-5.4-mini --tests-models deepseek-v4-flash gpt-5-mini
```

The commands are grouped by complexity level.

## Low

```powershell
python 0_run_pipeline.py --profile-id low --repo-model <repo-model> --tests-models <test-model-1> <test-model-2>
```

## High

```powershell
python 0_run_pipeline.py --profile-id high --repo-model <repo-model> --tests-models <test-model-1> <test-model-2>
```
