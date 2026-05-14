from __future__ import annotations

"""High-level evaluation runner for one or more generated test suites."""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from benchmark_pipeline.evaluation import EvaluationOutcome, evaluate_repositories, write_evaluation_json
from benchmark_pipeline.evaluation.reports import markdown_report
from benchmark_pipeline.models import GeneratedTests


@dataclass(frozen=True)
class EvaluationRunConfig:
    baseline_repo: Path
    tests_dir: Path
    report_json: Path
    report_md: Path
    pitest_report_dir: Path
    maven_cmd: Sequence[str]
    suite_generated_tests: dict[str, GeneratedTests] | None = None


@dataclass(frozen=True)
class EvaluationSuiteRun:
    suite_name: str
    suite_dir: Path
    report_json: Path
    report_md: Path
    pitest_report_dir: Path
    outcome: EvaluationOutcome


def discover_test_suites(tests_dir: Path) -> list[Path]:
    if not tests_dir.exists():
        raise FileNotFoundError(f"Tests directory not found: {tests_dir}")

    if (tests_dir / "src").exists() or (tests_dir / "pom.xml").exists():
        return [tests_dir]

    test_suites = [path for path in tests_dir.iterdir() if path.is_dir() and (path / "src").exists()]
    if not test_suites:
        raise FileNotFoundError(f"No valid test suites found in {tests_dir}")
    return sorted(test_suites)


def run_evaluation(config: EvaluationRunConfig) -> list[EvaluationSuiteRun]:
    if not config.baseline_repo.exists():
        raise FileNotFoundError(f"Baseline repository not found: {config.baseline_repo}")

    test_suites = discover_test_suites(config.tests_dir)
    is_direct_suite = (config.tests_dir / "src").exists() or (config.tests_dir / "pom.xml").exists()
    use_suite_named_reports = not is_direct_suite
    runs: list[EvaluationSuiteRun] = []

    for suite_dir in test_suites:
        suite_name = suite_dir.name if use_suite_named_reports else "evaluation"
        report_json = config.report_json.parent / f"{suite_name}_report.json" if use_suite_named_reports else config.report_json
        report_md = config.report_md.parent / f"{suite_name}_report.md" if use_suite_named_reports else config.report_md
        pitest_report_dir = config.pitest_report_dir / suite_name if use_suite_named_reports else config.pitest_report_dir

        print_evaluation_start(config, suite_name, suite_dir)
        outcome = evaluate_repositories(
            baseline_repo=config.baseline_repo,
            tests_dir=suite_dir,
            maven_cmd=config.maven_cmd,
            pitest_report_dir=pitest_report_dir,
        )
        generated_tests = config.suite_generated_tests.get(suite_name) if config.suite_generated_tests is not None else None
        write_evaluation_reports(report_json, report_md, outcome, generated_tests)
        print_evaluation_summary(suite_name, report_json, report_md, outcome)

        runs.append(
            EvaluationSuiteRun(
                suite_name=suite_name,
                suite_dir=suite_dir,
                report_json=report_json,
                report_md=report_md,
                pitest_report_dir=pitest_report_dir,
                outcome=outcome,
            )
        )

    return runs


def write_evaluation_reports(
    report_json: Path,
    report_md: Path,
    outcome: EvaluationOutcome,
    generated_tests: GeneratedTests | None = None,
) -> None:
    print(f"[evaluation] Writing JSON report to {report_json.resolve()}")
    write_evaluation_json(report_json, outcome)
    report_md.parent.mkdir(parents=True, exist_ok=True)
    print(f"[evaluation] Writing markdown report to {report_md.resolve()}")
    report_md.write_text(
        markdown_report(
            outcome.baseline_result,
            outcome.baseline_coverage,
            outcome.pitest_result,
            outcome.disabled_tests,
            outcome.initial_baseline_result,
            generated_tests,
        ),
        encoding="utf-8",
    )


def print_evaluation_start(config: EvaluationRunConfig, suite_name: str, suite_dir: Path) -> None:
    print()
    print("-" * 72)
    print(f"[evaluation] PIT mutation evaluation - {suite_name}")
    print("-" * 72)
    print(f"[evaluation] Baseline repository: {config.baseline_repo.resolve()}")
    print(f"[evaluation] Generated tests: {suite_dir.resolve()}")
    print(f"[evaluation] Running Maven verification with: {' '.join(config.maven_cmd)}")


def print_evaluation_summary(suite_name: str, report_json: Path, report_md: Path, outcome: EvaluationOutcome) -> None:
    print()
    print(f"[{suite_name}] Baseline repo passed: {outcome.baseline_result.passed}")
    print(f"[{suite_name}] Baseline run status: {outcome.baseline_result.status}")
    if outcome.disabled_tests:
        print(f"[{suite_name}] Disabled baseline-failing generated tests: {len(outcome.disabled_tests)}")
    if outcome.baseline_coverage is not None:
        print(f"[{suite_name}] Line coverage: {outcome.baseline_coverage.line_rate:.2%}")
        print(f"[{suite_name}] Branch coverage: {outcome.baseline_coverage.branch_rate:.2%}")
    mutation_score = outcome.pitest_result.mutation_score if outcome.pitest_result is not None else None
    if mutation_score is None:
        print(f"[{suite_name}] Mutation score: N/A")
    else:
        print(f"[{suite_name}] Mutation score: {mutation_score:.2%}")
    print(f"[{suite_name}] JSON report: {report_json.resolve()}")
    print(f"[{suite_name}] Markdown report: {report_md.resolve()}")
