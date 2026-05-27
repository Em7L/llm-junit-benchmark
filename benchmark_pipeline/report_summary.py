from __future__ import annotations

"""Aggregate comparison reports across benchmark runs."""

from collections import Counter
import csv
import json
from pathlib import Path
from statistics import fmean, stdev
from typing import Any

from benchmark_pipeline.fs_utils import dump_json


METRIC_KEYS = (
    "tests",
    "failures",
    "errors",
    "skipped",
    "disabled_tests",
    "line_coverage",
    "branch_coverage",
    "instruction_coverage",
    "total_mutations",
    "killed",
    "survived",
    "no_coverage",
    "mutation_score",
)


def find_comparison_reports(reports_root: Path) -> list[Path]:
    return sorted(reports_root.glob("**/reports/comparison_report.json"))


def load_comparison_reports(reports_root: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for report_path in find_comparison_reports(reports_root):
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        payload["_report_path"] = report_path.as_posix()
        payloads.append(payload)
    return payloads


def summarize_report_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    model_rows: dict[str, list[dict[str, Any]]] = {}
    profile_model_rows: dict[str, dict[str, list[dict[str, Any]]]] = {}
    repo_model_rows: dict[str, dict[str, list[dict[str, Any]]]] = {}
    repo_model_all_rows: dict[str, list[dict[str, Any]]] = {}
    appendix_rows: list[dict[str, Any]] = []

    for payload in payloads:
        profile = payload.get("benchmark_profile") or {}
        profile_id = str(profile.get("profile_id") or "auto-selected")
        repo_model = str(payload.get("repo_model") or "unknown")
        report_path = str(payload.get("_report_path") or "")
        rows = payload.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            model = str(row.get("test_model") or "unknown")
            model_rows.setdefault(model, []).append(row)
            profile_model_rows.setdefault(profile_id, {}).setdefault(model, []).append(row)
            repo_model_rows.setdefault(repo_model, {}).setdefault(model, []).append(row)
            repo_model_all_rows.setdefault(repo_model, []).append(row)
            appendix_rows.append(
                _appendix_row(
                    row,
                    profile_id=profile_id,
                    repo_model=repo_model,
                    report_path=report_path,
                )
            )

    summary = {
        "report_count": len(payloads),
        "report_paths": [str(payload["_report_path"]) for payload in payloads if "_report_path" in payload],
        "models": {
            model: summarize_model_rows(rows)
            for model, rows in sorted(model_rows.items())
        },
        "profiles": {
            profile_id: {
                "models": {
                    model: summarize_model_rows(rows)
                    for model, rows in sorted(models.items())
                }
            }
            for profile_id, models in sorted(profile_model_rows.items())
        },
        "repo_models": {
            repo_model: {
                "overall": summarize_model_rows(repo_model_all_rows.get(repo_model, [])),
                "models": {
                    model: summarize_model_rows(rows)
                    for model, rows in sorted(models.items())
                },
            }
            for repo_model, models in sorted(repo_model_rows.items())
        },
        "raw_rows": appendix_rows,
    }
    return summary


def summarize_model_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    generation_status_counts = Counter(_string_values(rows, "generation_status"))
    repair_outcome_counts = Counter(_string_values(rows, "repair_outcome"))
    disabling_outcome_counts = Counter(_string_values(rows, "disabling_outcome"))
    evaluation_status_counts = Counter(_string_values(rows, "evaluation_status"))

    generation_passes = generation_status_counts.get("passed", 0)
    accepted_rows = [row for row in rows if row.get("generation_status") == "passed"]
    evaluable_rows = sum(1 for row in rows if isinstance(row.get("evaluation_status"), str))
    final_passes = evaluation_status_counts.get("passed", 0)
    repaired_runs = sum(
        1 for row in rows if _repair_attempts_value(row) is not None and _repair_attempts_value(row) > 0
    )
    no_repair_runs = sum(
        1 for row in rows if _repair_attempts_value(row) == 0
    )
    initial_compile_passes = sum(
        1 for row in rows if _initial_suite_compiled(row)
    )
    final_compile_passes = sum(
        1 for row in rows if _final_suite_compiled(row)
    )
    final_compiled_rows = [row for row in rows if _final_suite_compiled(row)]
    final_before_disabling_passes = sum(
        1 for row in rows if _final_suite_passed_before_disabling(row)
    )
    final_disabling_not_needed = sum(
        1 for row in rows if row.get("disabling_outcome") == "disabling_not_needed"
    )
    generation_and_final_pass_without_repair = sum(
        1
        for row in rows
        if row.get("generation_status") == "passed"
        and _repair_attempts_value(row) == 0
        and _final_suite_passed_before_disabling(row)
    )
    compiled_final_before_disabling_passes = sum(
        1 for row in final_compiled_rows if _final_suite_passed_before_disabling(row)
    )
    compiled_final_passes = sum(
        1 for row in final_compiled_rows if row.get("evaluation_status") == "passed"
    )
    compiled_repaired_runs = sum(
        1 for row in final_compiled_rows if _repair_attempts_value(row) is not None and _repair_attempts_value(row) > 0
    )
    compiled_final_disabling_not_needed = sum(
        1 for row in final_compiled_rows if row.get("disabling_outcome") == "disabling_not_needed"
    )
    compiled_generation_and_final_pass_without_repair = sum(
        1
        for row in final_compiled_rows
        if row.get("generation_status") == "passed"
        and _repair_attempts_value(row) == 0
        and _final_suite_passed_before_disabling(row)
    )

    final_metric_stats = _metric_stats(rows, row_key=None)
    initial_metric_stats = _initial_metric_stats(rows)
    final_generated_suite_stats = _metric_stats(rows, row_key="final_generated_suite", snapshot_map=INITIAL_METRIC_MAP)
    repair_delta_metric_stats = _delta_stats(rows)

    repair_attempts = [value for value in (_numeric(row.get("repair_attempts")) for row in rows) if value is not None]

    return {
        "run_count": len(rows),
        "accepted_run_count": len(accepted_rows),
        "evaluable_run_count": evaluable_rows,
        "final_compiled_run_count": final_compile_passes,
        "generation_status_counts": dict(generation_status_counts),
        "repair_outcome_counts": dict(repair_outcome_counts),
        "disabling_outcome_counts": dict(disabling_outcome_counts),
        "evaluation_status_counts": dict(evaluation_status_counts),
        "accepted_suite_rate": _safe_rate(generation_passes, len(rows)),
        "initial_test_compile_rate": _safe_rate(initial_compile_passes, len(rows)),
        "final_test_compile_rate": _safe_rate(final_compile_passes, len(rows)),
        "final_before_disabling_pass_rate": _safe_rate(final_before_disabling_passes, len(rows)),
        "final_pass_rate": _safe_rate(final_passes, len(rows)),
        "repair_needed_rate": _safe_rate(repaired_runs, len(rows)),
        "no_repair_needed_rate": _safe_rate(no_repair_runs, len(rows)),
        "final_disabling_not_needed_rate": _safe_rate(final_disabling_not_needed, len(rows)),
        "generation_and_final_pass_without_repair_rate": _safe_rate(
            generation_and_final_pass_without_repair,
            len(rows),
        ),
        "compiled_final_before_disabling_pass_rate": _safe_rate(
            compiled_final_before_disabling_passes,
            final_compile_passes,
        ),
        "compiled_final_pass_rate": _safe_rate(compiled_final_passes, final_compile_passes),
        "compiled_repair_needed_rate": _safe_rate(compiled_repaired_runs, final_compile_passes),
        "compiled_final_disabling_not_needed_rate": _safe_rate(
            compiled_final_disabling_not_needed,
            final_compile_passes,
        ),
        "compiled_generation_and_final_pass_without_repair_rate": _safe_rate(
            compiled_generation_and_final_pass_without_repair,
            final_compile_passes,
        ),
        "repaired_run_count": repaired_runs,
        "no_repair_run_count": no_repair_runs,
        "mean_repair_attempts": fmean(repair_attempts) if repair_attempts else None,
        "final_means": _metric_means_from_stats(final_metric_stats),
        "initial_means": _metric_means_from_stats(initial_metric_stats),
        "final_generated_suite_means": _metric_means_from_stats(final_generated_suite_stats),
        "repair_delta_means": _metric_means_from_stats(repair_delta_metric_stats),
        "final_stats": final_metric_stats,
        "initial_stats": initial_metric_stats,
        "final_generated_suite_stats": final_generated_suite_stats,
        "repair_delta_stats": repair_delta_metric_stats,
    }


INITIAL_METRIC_MAP = {
    "tests": "after_tests",
    "failures": "after_failures",
    "errors": "after_errors",
    "skipped": "after_skipped",
    "disabled_tests": "disabled_tests",
    "line_coverage": "line_coverage",
    "branch_coverage": "branch_coverage",
    "instruction_coverage": "instruction_coverage",
    "total_mutations": "total_mutations",
    "killed": "killed",
    "survived": "survived",
    "no_coverage": "no_coverage",
    "mutation_score": "mutation_score",
}


FINAL_SNAPSHOT_MAP = {
    "tests": "after_tests",
    "failures": "after_failures",
    "errors": "after_errors",
    "skipped": "after_skipped",
    "disabled_tests": "disabled_tests",
    "line_coverage": "line_coverage",
    "branch_coverage": "branch_coverage",
    "instruction_coverage": "instruction_coverage",
    "total_mutations": "total_mutations",
    "killed": "killed",
    "survived": "survived",
    "no_coverage": "no_coverage",
    "mutation_score": "mutation_score",
}


def _metric_stats(
    rows: list[dict[str, Any]],
    *,
    row_key: str | None,
    snapshot_map: dict[str, str] | None = None,
) -> dict[str, dict[str, float | int | None]]:
    metric_values: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for row in rows:
        source: Any = row
        if row_key is not None:
            source = row.get(row_key)
            if not isinstance(source, dict):
                continue
        for key in METRIC_KEYS:
            value_key = snapshot_map.get(key, key) if snapshot_map is not None else key
            value = _numeric(source.get(value_key)) if isinstance(source, dict) else None
            if value is not None:
                metric_values[key].append(value)
    return {
        key: _summarize_values(values)
        for key, values in metric_values.items()
    }


def _initial_metric_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int | None]]:
    metric_values: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for row in rows:
        source = _initial_metrics_source(row)
        if source is None:
            continue
        for key in METRIC_KEYS:
            value_key = INITIAL_METRIC_MAP.get(key, key)
            value = _numeric(source.get(value_key))
            if value is not None:
                metric_values[key].append(value)
    return {
        key: _summarize_values(values)
        for key, values in metric_values.items()
    }


def _delta_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int | None]]:
    delta_values: dict[str, list[float]] = {
        "tests": [],
        "skipped": [],
        "disabled_tests": [],
        "line_coverage": [],
        "branch_coverage": [],
        "instruction_coverage": [],
        "total_mutations": [],
        "killed": [],
        "survived": [],
        "no_coverage": [],
        "mutation_score": [],
    }
    for row in rows:
        repair_attempts = _numeric(row.get("repair_attempts"))
        if repair_attempts is None or repair_attempts <= 0:
            continue
        before = row.get("initial_generated_suite")
        after = row.get("final_generated_suite")
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        for metric, before_key in FINAL_SNAPSHOT_MAP.items():
            if metric not in delta_values:
                continue
            before_value = _numeric(before.get(before_key))
            after_value = _numeric(after.get(before_key))
            if before_value is None or after_value is None:
                continue
            delta_values[metric].append(after_value - before_value)
    return {
        key: _summarize_values(values)
        for key, values in delta_values.items()
    }


def _metric_means_from_stats(
    metric_stats: dict[str, dict[str, float | int | None]],
) -> dict[str, float | None]:
    return {
        key: _numeric(stats.get("mean")) if isinstance(stats, dict) else None
        for key, stats in metric_stats.items()
    }


def _summarize_values(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "stdev": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": fmean(values),
        "stdev": stdev(values) if len(values) > 1 else None,
        "min": min(values),
        "max": max(values),
    }


def _string_values(rows: list[dict[str, Any]], key: str) -> list[str]:
    return [value for value in (row.get(key) for row in rows) if isinstance(value, str)]


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator else None


def _repair_attempts_value(row: dict[str, Any]) -> float | None:
    return _numeric(row.get("repair_attempts"))


def _initial_suite_compiled(row: dict[str, Any]) -> bool:
    snapshot = _initial_metrics_source(row)
    if not isinstance(snapshot, dict):
        return False
    return snapshot.get("before_disabling_status") != "test_compile_failure"


def _final_suite_compiled(row: dict[str, Any]) -> bool:
    status = row.get("final_suite_before_disabling_status")
    return isinstance(status, str) and status != "test_compile_failure"


def _final_suite_passed_before_disabling(row: dict[str, Any]) -> bool:
    status = row.get("final_suite_before_disabling_status")
    return status == "passed"


def _initial_metrics_source(row: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = row.get("initial_generated_suite")
    if isinstance(snapshot, dict):
        return snapshot

    if row.get("repair_attempts") == 0:
        final_snapshot = row.get("final_generated_suite")
        if isinstance(final_snapshot, dict):
            return final_snapshot
    return None


def format_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Comparison Report Summary",
        "",
        f"- Reports aggregated: `{summary['report_count']}`",
        "- JSON remains the canonical machine-readable record; this Markdown is a thesis-oriented human-readable view of the same aggregated data.",
    ]

    model_summaries = summary.get("models", {})
    if isinstance(model_summaries, dict) and model_summaries:
        lines.extend(_render_rq_overview(summary))
        lines.extend(_render_key_findings(model_summaries))
        lines.extend(_render_overall_usability_table(model_summaries))
        lines.extend(_render_overall_effectiveness_table(model_summaries))

    profiles = summary.get("profiles", {})
    repo_models = summary.get("repo_models", {})
    if isinstance(profiles, dict) and isinstance(repo_models, dict) and profiles and repo_models:
        lines.extend(_render_condition_sensitivity_section(profiles, repo_models))

    if isinstance(model_summaries, dict) and model_summaries:
        lines.extend(_render_variability_and_repair_section(model_summaries))
    return "\n".join(lines)


def write_summary_files(summary: dict[str, Any], *, output_json: Path | None, output_md: Path | None) -> None:
    # The summary JSON payload is the canonical aggregated record.
    # Markdown is rendered purely as a human-readable view of that same payload.
    canonical_summary = summary
    if output_json is not None:
        dump_json(output_json, canonical_summary)
    if output_md is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(format_summary_markdown(canonical_summary), encoding="utf-8")


def write_appendix_files(summary: dict[str, Any], *, output_csv: Path | None, output_md: Path | None) -> None:
    raw_rows = summary.get("raw_rows", [])
    if not isinstance(raw_rows, list):
        raw_rows = []
    if output_csv is not None:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = APPENDIX_FIELDNAMES
        with output_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in raw_rows:
                writer.writerow({field: row.get(field) for field in fieldnames})
    if output_md is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(format_appendix_markdown(raw_rows), encoding="utf-8")


def _cell(value: Any) -> str:
    return "N/A" if value is None else str(value)


def _percent(value: Any) -> str:
    return "N/A" if not isinstance(value, int | float) else f"{value:.2%}"


def _number(value: Any, digits: int) -> str:
    return "N/A" if not isinstance(value, int | float) else f"{value:.{digits}f}"


def _render_compact_variability_table(title: str, model_summaries: dict[str, Any]) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| Test model | n | Line cov. sd | Branch cov. sd | Mutation sd |",
        "|---|---:|---:|---:|---:|",
    ]
    for model, model_summary in sorted(model_summaries.items()):
        final_stats = model_summary.get("final_stats", {})
        line_stats = final_stats.get("line_coverage", {})
        branch_stats = final_stats.get("branch_coverage", {})
        mutation_stats = final_stats.get("mutation_score", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    _cell(line_stats.get("n")),
                    _percent(line_stats.get("stdev")),
                    _percent(branch_stats.get("stdev")),
                    _percent(mutation_stats.get("stdev")),
                ]
            )
            + " |"
        )
    return lines


def _render_repair_effects_table(title: str, model_summaries: dict[str, Any]) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| Test model | Repaired runs | Delta line cov. | Delta branch cov. | Delta mutation score |",
        "|---|---:|---:|---:|---:|",
    ]
    for model, model_summary in sorted(model_summaries.items()):
        metrics = model_summary.get("repair_delta_means", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    _cell(model_summary.get("repaired_run_count")),
                    _percent(metrics.get("line_coverage")),
                    _percent(metrics.get("branch_coverage")),
                    _percent(metrics.get("mutation_score")),
                ]
            )
            + " |"
        )
    return lines


def _render_rq_overview(summary: dict[str, Any]) -> list[str]:
    return [
        "",
        "## RQ Coverage Map",
        "",
        "| RQ | Summary sections to read |",
        "|---|---|",
        "| RQ1. Usability | `RQ1. Usability` |",
        "| RQ2. Structural reach | `RQ2/RQ3. Coverage and Mutation` |",
        "| RQ3. Fault-detection strength | `RQ2/RQ3. Coverage and Mutation` |",
        "| RQ4. Condition sensitivity | `RQ4. Condition Sensitivity` |",
    ]


def _render_key_findings(model_summaries: dict[str, Any]) -> list[str]:
    best_mutation = _best_model(model_summaries, lambda summary: summary.get("final_means", {}).get("mutation_score"))
    best_line = _best_model(model_summaries, lambda summary: summary.get("final_means", {}).get("line_coverage"))
    best_usability = _best_model(model_summaries, lambda summary: summary.get("final_test_compile_rate"))
    highest_variability = _best_model(
        model_summaries,
        lambda summary: summary.get("final_stats", {}).get("mutation_score", {}).get("stdev"),
    )
    lines = [
        "",
        "## Key Findings",
        "",
    ]
    if best_mutation is not None:
        lines.append(
            f"- Highest average mutation score: `{best_mutation}` with {_percent(model_summaries[best_mutation].get('final_means', {}).get('mutation_score'))}."
        )
    if best_line is not None:
        lines.append(
            f"- Highest average line coverage: `{best_line}` with {_percent(model_summaries[best_line].get('final_means', {}).get('line_coverage'))}."
        )
    if best_usability is not None:
        lines.append(
            f"- Best final compile rate: `{best_usability}` with {_percent(model_summaries[best_usability].get('final_test_compile_rate'))}."
        )
    if highest_variability is not None:
        lines.append(
            f"- Highest mutation-score variability: `{highest_variability}` with SD {_percent(model_summaries[highest_variability].get('final_stats', {}).get('mutation_score', {}).get('stdev'))}."
        )
    return lines


def _render_overall_usability_table(model_summaries: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## RQ1. Usability",
        "",
        "### Compilation Rates (All Generated-Suite Attempts)",
        "",
        "| Test model | n | Initial compile rate | Final compile rate |",
        "|---|---:|---:|---:|",
    ]
    for model, model_summary in sorted(model_summaries.items()):
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    _cell(model_summary.get("run_count")),
                    _percent(model_summary.get("initial_test_compile_rate")),
                    _percent(model_summary.get("final_test_compile_rate")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "### Evaluation and Repair Rates (Final Compiled Suites Only)",
            "",
            "| Test model | n compiled | Pre-disable pass rate | Repair needed |",
            "|---|---:|---:|---:|",
        ]
    )
    for model, model_summary in sorted(model_summaries.items()):
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    _cell(model_summary.get("final_compiled_run_count")),
                    _percent(model_summary.get("compiled_final_before_disabling_pass_rate")),
                    _percent(model_summary.get("compiled_repair_needed_rate")),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("Note: the second table is conditioned on final compiled suites only.")
    compiled_pass_rates = [
        model_summary.get("compiled_final_pass_rate")
        for model_summary in model_summaries.values()
        if model_summary.get("final_compiled_run_count")
    ]
    if compiled_pass_rates and all(rate == 1 for rate in compiled_pass_rates):
        lines.append(
            "Note: the final staged pass rate is 100.00% for every model in this dataset, so it is omitted from the table."
        )
    return lines


def _render_overall_effectiveness_table(model_summaries: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## RQ2/RQ3. Coverage and Mutation",
        "",
        "### RQ2. Coverage",
        "",
        "| Test model | n | Avg tests | Line cov. mean | Branch cov. mean | Line cov. range | Branch cov. range |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model, model_summary in sorted(model_summaries.items()):
        final_stats = model_summary.get("final_stats", {})
        line_stats = final_stats.get("line_coverage", {})
        branch_stats = final_stats.get("branch_coverage", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    _cell(line_stats.get("n")),
                    _number(model_summary.get("final_means", {}).get("tests"), 2),
                    _percent(line_stats.get("mean")),
                    _percent(branch_stats.get("mean")),
                    _range_percent(line_stats.get("min"), line_stats.get("max")),
                    _range_percent(branch_stats.get("min"), branch_stats.get("max")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "### RQ3. Mutation",
            "",
            "| Test model | n | Avg tests | Mutation mean | Mutation range |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for model, model_summary in sorted(model_summaries.items()):
        final_stats = model_summary.get("final_stats", {})
        mutation_stats = final_stats.get("mutation_score", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    _cell(mutation_stats.get("n")),
                    _number(model_summary.get("final_means", {}).get("tests"), 2),
                    _percent(mutation_stats.get("mean")),
                    _range_percent(mutation_stats.get("min"), mutation_stats.get("max")),
                ]
            )
            + " |"
        )
    return lines


def _range_percent(min_value: Any, max_value: Any) -> str:
    if not isinstance(min_value, int | float) or not isinstance(max_value, int | float):
        return "N/A"
    return f"{min_value:.2%}..{max_value:.2%}"


def _render_condition_sensitivity_section(profiles: dict[str, Any], repo_models: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## RQ4. Condition Sensitivity",
        "",
        "### Complexity Conditions",
        "",
        "| Test model | High line cov. | Low line cov. | High branch cov. | Low branch cov. | High mutation | Low mutation |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    high_models = profiles.get("high", {}).get("models", {})
    low_models = profiles.get("low", {}).get("models", {})
    for model in sorted(set(high_models) & set(low_models)):
        high_summary = high_models.get(model, {})
        low_summary = low_models.get(model, {})
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    _percent(high_summary.get("final_means", {}).get("line_coverage")),
                    _percent(low_summary.get("final_means", {}).get("line_coverage")),
                    _percent(high_summary.get("final_means", {}).get("branch_coverage")),
                    _percent(low_summary.get("final_means", {}).get("branch_coverage")),
                    _percent(high_summary.get("final_means", {}).get("mutation_score")),
                    _percent(low_summary.get("final_means", {}).get("mutation_score")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "### Repository-Generation Models",
            "",
            "| Test model | DeepSeek repo line cov. | GPT-5.4 repo line cov. | DeepSeek repo branch cov. | GPT-5.4 repo branch cov. | DeepSeek repo mutation | GPT-5.4 repo mutation |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    ds_models = repo_models.get("deepseek-v4-flash", {}).get("models", {})
    gpt_models = repo_models.get("gpt-5.4-mini", {}).get("models", {})
    for model in sorted(set(ds_models) & set(gpt_models)):
        ds_summary = ds_models.get(model, {})
        gpt_summary = gpt_models.get(model, {})
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    _percent(ds_summary.get("final_means", {}).get("line_coverage")),
                    _percent(gpt_summary.get("final_means", {}).get("line_coverage")),
                    _percent(ds_summary.get("final_means", {}).get("branch_coverage")),
                    _percent(gpt_summary.get("final_means", {}).get("branch_coverage")),
                    _percent(ds_summary.get("final_means", {}).get("mutation_score")),
                    _percent(gpt_summary.get("final_means", {}).get("mutation_score")),
                ]
            )
            + " |"
        )
    return lines


def _render_variability_and_repair_section(model_summaries: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Metric Definitions",
        "",
        "- `Accepted suite`: generated test suite that parsed into the expected structured schema and passed the pipeline's semantic checks, possibly after semantic-repair attempts. Unparseable outputs are generation failures and are not repaired; parsed outputs that still fail semantic validation after the repair budget do not continue to Maven evaluation.",
        "- `Initial suite`: first accepted version of a generated test suite before verification-time repair changes.",
        "- `Final suite`: retained generated test suite after available semantic and verification-time repair steps.",
        "- `Initial compile rate`: proportion of all generated-suite attempts that produced an accepted initial suite and whose initial accepted suite compiled before staged disabling.",
        "- `Final compile rate`: proportion of all generated-suite attempts that produced an accepted final retained suite and whose final retained suite compiled before staged disabling.",
        "- `Pre-disable pass rate`: share of final compiled suites that passed all tests before any failing or erroring generated tests were disabled. The complement is the share with at least one generated test failure or error before staged disabling.",
        "- `Repair needed`: among final compiled suites, proportion that triggered at least one automatic repair attempt.",
        "- Coverage and mutation means use only rows where the corresponding JaCoCo or PIT value exists; non-accepted or non-evaluable runs appear as `N/A` in the appendix.",
        "",
        "## Variability and Repair",
        "",
        "### Variability",
        "",
        "| Test model | n | Line cov. sd | Branch cov. sd | Mutation sd |",
        "|---|---:|---:|---:|---:|",
    ]
    for model, model_summary in sorted(model_summaries.items()):
        final_stats = model_summary.get("final_stats", {})
        line_stats = final_stats.get("line_coverage", {})
        branch_stats = final_stats.get("branch_coverage", {})
        mutation_stats = final_stats.get("mutation_score", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    _cell(line_stats.get("n")),
                    _percent(line_stats.get("stdev")),
                    _percent(branch_stats.get("stdev")),
                    _percent(mutation_stats.get("stdev")),
                ]
            )
            + " |"
        )
    lines.extend(_render_repair_effects_table("Repair Effects (Repaired Runs Only)", model_summaries))
    return lines


def _best_model(
    model_summaries: dict[str, Any],
    metric_getter: Any,
) -> str | None:
    best_name: str | None = None
    best_value: float | None = None
    for model, summary in sorted(model_summaries.items()):
        value = metric_getter(summary)
        if not isinstance(value, int | float):
            continue
        if best_value is None or value > best_value:
            best_name = model
            best_value = float(value)
    return best_name


APPENDIX_FIELDNAMES = [
    "profile_id",
    "repo_model",
    "run_id",
    "test_model",
    "generation_status",
    "repair_attempts",
    "repair_outcome",
    "accepted",
    "initial_compiled",
    "final_compiled",
    "final_pre_disable_passed",
    "final_staged_passed",
    "no_disabling_needed",
    "line_coverage",
    "branch_coverage",
    "mutation_score",
    "report_path",
]


def _appendix_row(
    row: dict[str, Any],
    *,
    profile_id: str,
    repo_model: str,
    report_path: str,
) -> dict[str, Any]:
    run_id = _run_id_from_report_path(report_path)
    return {
        "profile_id": profile_id,
        "repo_model": repo_model,
        "run_id": run_id,
        "test_model": row.get("test_model"),
        "generation_status": row.get("generation_status"),
        "repair_attempts": row.get("repair_attempts"),
        "repair_outcome": row.get("repair_outcome"),
        "accepted": row.get("generation_status") == "passed",
        "initial_compiled": _initial_suite_compiled(row),
        "final_compiled": _final_suite_compiled(row),
        "final_pre_disable_passed": _final_suite_passed_before_disabling(row),
        "final_staged_passed": row.get("evaluation_status") == "passed",
        "no_disabling_needed": row.get("disabling_outcome") == "disabling_not_needed",
        "line_coverage": row.get("line_coverage"),
        "branch_coverage": row.get("branch_coverage"),
        "mutation_score": row.get("mutation_score"),
        "report_path": report_path,
    }


def _run_id_from_report_path(report_path: str) -> str:
    if not report_path:
        return "unknown"
    path = Path(report_path)
    try:
        return path.parents[1].name
    except IndexError:
        return "unknown"


def format_appendix_markdown(raw_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Comparison Report Appendix",
        "",
        f"- Per-run rows exported: `{len(raw_rows)}`",
        "",
        "| Profile | Repo model | Run | Test model | Generation | Repairs | Accepted | Final compile | Line cov. | Branch cov. | Mutation |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in raw_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("profile_id", "N/A")),
                    str(row.get("repo_model", "N/A")),
                    str(row.get("run_id", "N/A")),
                    str(row.get("test_model", "N/A")),
                    str(row.get("generation_status", "N/A")),
                    _cell(row.get("repair_attempts")),
                    _bool_cell(row.get("accepted")),
                    _bool_cell(row.get("final_compiled")),
                    _percent(row.get("line_coverage")),
                    _percent(row.get("branch_coverage")),
                    _percent(row.get("mutation_score")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _bool_cell(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "N/A"
