# Benchmark Profile Commands

This file lists the `4` benchmark-profile commands derived from the current domain-only benchmark frame.

Use this command template:

```powershell
python 0_run_pipeline.py --profile-id <profile-id> --repo-model <repo-model> --tests-models <test-model-1> <test-model-2>
```

Example with concrete models:

```powershell
python 0_run_pipeline.py --profile-id library --repo-model gpt-5.4-mini --tests-models deepseek-v4-flash gpt-5-mini
```

The commands are grouped by domain.

## Library

```powershell
python 0_run_pipeline.py --profile-id library --repo-model <repo-model> --tests-models <test-model-1> <test-model-2>
```

## Meal-Planning

```powershell
python 0_run_pipeline.py --profile-id meal-planning --repo-model <repo-model> --tests-models <test-model-1> <test-model-2>
```

## Inventory

```powershell
python 0_run_pipeline.py --profile-id inventory --repo-model <repo-model> --tests-models <test-model-1> <test-model-2>
```

## Billing

```powershell
python 0_run_pipeline.py --profile-id billing --repo-model <repo-model> --tests-models <test-model-1> <test-model-2>
```
