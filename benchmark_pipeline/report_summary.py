from __future__ import annotations

"""Aggregate comparison reports across benchmark runs."""

from collections import Counter
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

    for payload in payloads:
        profile = payload.get("benchmark_profile") or {}
        profile_id = str(profile.get("profile_id") or "auto-selected")
        rows = payload.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            model = str(row.get("test_model") or "unknown")
            model_rows.setdefault(model, []).append(row)
            profile_model_rows.setdefault(profile_id, {}).setdefault(model, []).append(row)

    return {
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
    }


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
        1 for row in rows if (_numeric(row.get("repair_attempts")) or 0) > 0
    )
    initial_compile_passes = sum(
        1 for row in accepted_rows if _initial_suite_compiled(row)
    )
    final_compile_passes = sum(
        1 for row in accepted_rows if _final_suite_compiled(row)
    )

    final_metric_stats = _metric_stats(rows, row_key=None)
    initial_metric_stats = _metric_stats(rows, row_key="initial_generated_suite", snapshot_map=INITIAL_METRIC_MAP)
    final_generated_suite_stats = _metric_stats(rows, row_key="final_generated_suite", snapshot_map=INITIAL_METRIC_MAP)
    repair_delta_metric_stats = _delta_stats(rows)

    repair_attempts = [value for value in (_numeric(row.get("repair_attempts")) for row in rows) if value is not None]

    return {
        "run_count": len(rows),
        "generation_status_counts": dict(generation_status_counts),
        "repair_outcome_counts": dict(repair_outcome_counts),
        "disabling_outcome_counts": dict(disabling_outcome_counts),
        "evaluation_status_counts": dict(evaluation_status_counts),
        "accepted_suite_rate": _safe_rate(generation_passes, len(rows)),
        "initial_test_compile_rate": _safe_rate(initial_compile_passes, len(accepted_rows)),
        "final_test_compile_rate": _safe_rate(final_compile_passes, len(accepted_rows)),
        "final_pass_rate": _safe_rate(final_passes, evaluable_rows),
        "repair_needed_rate": _safe_rate(repaired_runs, len(rows)),
        "repaired_run_count": repaired_runs,
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


def _initial_suite_compiled(row: dict[str, Any]) -> bool:
    snapshot = row.get("initial_generated_suite")
    if not isinstance(snapshot, dict):
        return False
    return snapshot.get("before_disabling_status") != "test_compile_failure"


def _final_suite_compiled(row: dict[str, Any]) -> bool:
    status = row.get("final_suite_before_disabling_status")
    return isinstance(status, str) and status != "test_compile_failure"


def format_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Comparison Report Summary",
        "",
        f"- Reports aggregated: `{summary['report_count']}`",
    ]

    model_summaries = summary.get("models", {})
    if isinstance(model_summaries, dict) and model_summaries:
        lines.extend(
            [
                "",
                "## Overall Results",
                "",
                "| Test model | Runs | Accepted suite rate | Initial test compile rate | Final test compile rate | Final pass rate | Repair needed | Avg tests | Avg line cov. | Avg branch cov. | Avg mutation score |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for model, model_summary in sorted(model_summaries.items()):
            lines.append(
                "| "
                + " | ".join(
                    [
                        model,
                        _cell(model_summary.get("run_count")),
                        _percent(model_summary.get("accepted_suite_rate")),
                        _percent(model_summary.get("initial_test_compile_rate")),
                        _percent(model_summary.get("final_test_compile_rate")),
                        _percent(model_summary.get("final_pass_rate")),
                        _percent(model_summary.get("repair_needed_rate")),
                        _number(model_summary.get("final_means", {}).get("tests"), 2),
                        _percent(model_summary.get("final_means", {}).get("line_coverage")),
                        _percent(model_summary.get("final_means", {}).get("branch_coverage")),
                        _percent(model_summary.get("final_means", {}).get("mutation_score")),
                    ]
                )
                + " |"
            )
        lines.extend(
                [
                    "",
                    "Note: `Accepted suite rate` means the pipeline accepted a generated suite artifact for downstream evaluation; it is not a compile metric. "
                    "`Initial test compile rate` and `Final test compile rate` measure whether the generated test suite compiled before staged disabling. "
                    "`Final pass rate` uses the benchmark's staged evaluation rule. "
                    "If generated tests fail on the accepted baseline repository and the failing tests can be identified, "
                    "those failing generated tests may be disabled in the temporary staged evaluation copy before final coverage and PIT evaluation.",
                ]
        )
        lines.extend(_render_compact_variability_table("Overall Variability", model_summaries))
        lines.extend(_render_repair_effects_table("Repair Effects (Repaired Runs Only)", model_summaries))

    profiles = summary.get("profiles", {})
    if isinstance(profiles, dict):
        for profile_id, profile_summary in sorted(profiles.items()):
            lines.extend(
                [
                    "",
                    f"## Profile `{profile_id}`",
                    "",
                    "| Test model | Runs | Initial test compile rate | Final test compile rate | Final pass rate | Repair needed | Avg tests | Avg line cov. | Avg branch cov. | Avg mutation score |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            models = profile_summary.get("models", {})
            if isinstance(models, dict):
                for model, model_summary in sorted(models.items()):
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                model,
                                _cell(model_summary.get("run_count")),
                                _percent(model_summary.get("initial_test_compile_rate")),
                                _percent(model_summary.get("final_test_compile_rate")),
                                _percent(model_summary.get("final_pass_rate")),
                                _percent(model_summary.get("repair_needed_rate")),
                                _number(model_summary.get("final_means", {}).get("tests"), 2),
                                _percent(model_summary.get("final_means", {}).get("line_coverage")),
                                _percent(model_summary.get("final_means", {}).get("branch_coverage")),
                                _percent(model_summary.get("final_means", {}).get("mutation_score")),
                            ]
                        )
                        + " |"
                    )
                lines.extend(_render_compact_variability_table(f"Profile `{profile_id}` Variability", models))
    return "\n".join(lines)


def write_summary_files(summary: dict[str, Any], *, output_json: Path | None, output_md: Path | None) -> None:
    if output_json is not None:
        dump_json(output_json, summary)
    if output_md is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(format_summary_markdown(summary), encoding="utf-8")


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
