from __future__ import annotations

"""Shared classification taxonomy and outcome-comparison helpers."""

from benchmark_pipeline.models import MavenResult


GENERATION_CLASSIFICATIONS: dict[str, str] = {
    "passed": "The test-generation step produced a suite artifact that the pipeline accepted for downstream evaluation.",
    "failed": "The test-generation step did not produce an accepted suite artifact for downstream evaluation.",
    "missing": "The pipeline expected a generated suite outcome here, but no accepted suite artifact was available.",
}


REPAIR_CLASSIFICATIONS: dict[str, str] = {
    "repair_not_needed": "The initial generated test suite already passed verification, so no repair attempt was needed.",
    "repair_successful": "One or more repair attempts were applied and the final generated test suite passed verification.",
    "repair_partially_improved": "One or more repair attempts improved the verification outcome, but the final generated test suite still did not pass verification.",
    "repair_no_improvement": "One or more repair attempts were applied, but the final generated test suite did not verify any better than the first verifiable suite.",
    "repair_regressed": "One or more repair attempts were applied and the final generated test suite verified worse than the first verifiable suite.",
    "repair_discarded_incomplete": "A repair response was rejected because it returned an incomplete suite, and the pipeline kept the last complete suite instead.",
}


MAVEN_STATUS_CLASSIFICATIONS: dict[str, str] = {
    "passed": "The Maven validation run completed successfully with no remaining failing or errored tests.",
    "test_failures": "The tests compiled and ran, but at least one test assertion failed.",
    "test_execution_failure": "The tests compiled, but the Maven test execution phase failed before a normal passing/failing outcome was completed.",
    "test_compile_failure": "The generated or existing test sources did not compile during Maven test validation.",
    "main_compile_failure": "The main production sources did not compile during Maven validation.",
    "maven_failure": "The Maven run failed for a broader build reason that was not classified as a main-compile, test-compile, or ordinary test-failure outcome.",
    "missing": "The pipeline expected an evaluation result here, but no evaluation outcome was available.",
}


DISABLING_CLASSIFICATIONS: dict[str, str] = {
    "disabling_not_needed": "No baseline-failing generated tests had to be disabled before mutation evaluation.",
    "disabling_not_applicable": "Disabling baseline-failing tests was not applicable because evaluation did not reach the stage where named failing tests could be disabled.",
    "disabling_applied_successful": "Disabling baseline-failing generated tests resulted in a passing final baseline test suite.",
    "disabling_applied_partial": "Disabling baseline-failing generated tests improved the baseline verification outcome, but the final suite still did not pass.",
    "disabling_applied_no_effect": "Disabling baseline-failing generated tests did not improve the final baseline verification outcome.",
    "disabling_applied_regressed": "Disabling baseline-failing generated tests made the final baseline verification outcome worse.",
}


_STATUS_RANK: dict[str, int] = {
    "passed": 0,
    "test_failures": 1,
    "test_execution_failure": 2,
    "test_compile_failure": 3,
    "main_compile_failure": 4,
    "maven_failure": 5,
}


def compare_maven_results(before: MavenResult, after: MavenResult) -> str:
    before_score = maven_result_score(before)
    after_score = maven_result_score(after)
    if after_score < before_score:
        return "improved"
    if after_score > before_score:
        return "worse"
    return "same"


def maven_result_score(result: MavenResult) -> tuple[int, int, int, int, int]:
    failures_and_errors = result.failures + result.errors
    return (
        _STATUS_RANK.get(result.status, 99),
        failures_and_errors,
        result.errors,
        result.failures,
        result.exit_code,
    )


def classify_repair(
    *,
    repair_attempts: int,
    first_verification_result: MavenResult | None,
    final_verification_result: MavenResult | None,
    final_repair_discarded: bool,
) -> str:
    if repair_attempts == 0:
        return "repair_not_needed"
    if final_repair_discarded:
        return "repair_discarded_incomplete"
    if final_verification_result is not None and final_verification_result.passed:
        return "repair_successful"
    if first_verification_result is None or final_verification_result is None:
        return "repair_no_improvement"

    comparison = compare_maven_results(first_verification_result, final_verification_result)
    if comparison == "improved":
        return "repair_partially_improved"
    if comparison == "worse":
        return "repair_regressed"
    return "repair_no_improvement"


def classify_disabling(
    *,
    baseline_result: MavenResult,
    disabled_tests: list[str] | None = None,
    initial_baseline_result: MavenResult | None = None,
) -> str:
    if initial_baseline_result is None:
        return "disabling_not_needed" if baseline_result.passed else "disabling_not_applicable"
    if baseline_result.passed:
        return "disabling_applied_successful"

    comparison = compare_maven_results(initial_baseline_result, baseline_result)
    if comparison == "improved":
        return "disabling_applied_partial"
    if comparison == "worse":
        return "disabling_applied_regressed"
    return "disabling_applied_no_effect"


def selected_definitions(definitions: dict[str, str], names: list[str]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    selected: list[tuple[str, str]] = []
    for name in names:
        if name in definitions and name not in seen:
            selected.append((name, definitions[name]))
            seen.add(name)
    return selected
