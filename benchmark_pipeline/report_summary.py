from __future__ import annotations

"""Aggregate comparison reports across benchmark runs."""

from collections import Counter
import json
from pathlib import Path
from statistics import fmean
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
    evaluable_rows = sum(1 for row in rows if isinstance(row.get("evaluation_status"), str))
    final_passes = evaluation_status_counts.get("passed", 0)

    final_metrics = _metric_means(rows, row_key=None)
    initial_metrics = _metric_means(rows, row_key="before_repair", snapshot_map=INITIAL_METRIC_MAP)
    repair_delta_metrics = _delta_means(rows)

    repair_attempts = [value for value in (_numeric(row.get("repair_attempts")) for row in rows) if value is not None]

    return {
        "run_count": len(rows),
        "generation_status_counts": dict(generation_status_counts),
        "repair_outcome_counts": dict(repair_outcome_counts),
        "disabling_outcome_counts": dict(disabling_outcome_counts),
        "evaluation_status_counts": dict(evaluation_status_counts),
        "generation_pass_rate": _safe_rate(generation_passes, len(rows)),
        "final_pass_rate": _safe_rate(final_passes, evaluable_rows),
        "mean_repair_attempts": fmean(repair_attempts) if repair_attempts else None,
        "final_means": final_metrics,
        "initial_means": initial_metrics,
        "repair_delta_means": repair_delta_metrics,
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


def _metric_means(
    rows: list[dict[str, Any]],
    *,
    row_key: str | None,
    snapshot_map: dict[str, str] | None = None,
) -> dict[str, float | None]:
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
        key: (fmean(values) if values else None)
        for key, values in metric_values.items()
    }


def _delta_means(rows: list[dict[str, Any]]) -> dict[str, float | None]:
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
        before = row.get("before_repair")
        after = row.get("after_repair")
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
        key: (fmean(values) if values else None)
        for key, values in delta_values.items()
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
                "## Overall Model Averages",
                "",
                "| Test model | Runs | Gen pass rate | Final pass rate | Avg repair tries | Avg tests | Avg line cov. | Avg branch cov. | Avg mutation score |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for model, model_summary in sorted(model_summaries.items()):
            lines.append(
                "| "
                + " | ".join(
                    [
                        model,
                        _cell(model_summary.get("run_count")),
                        _percent(model_summary.get("generation_pass_rate")),
                        _percent(model_summary.get("final_pass_rate")),
                        _number(model_summary.get("mean_repair_attempts"), 2),
                        _number(model_summary.get("final_means", {}).get("tests"), 2),
                        _percent(model_summary.get("final_means", {}).get("line_coverage")),
                        _percent(model_summary.get("final_means", {}).get("branch_coverage")),
                        _percent(model_summary.get("final_means", {}).get("mutation_score")),
                    ]
                )
                + " |"
            )

    profiles = summary.get("profiles", {})
    if isinstance(profiles, dict):
        for profile_id, profile_summary in sorted(profiles.items()):
            lines.extend(
                [
                    "",
                    f"## Profile `{profile_id}`",
                    "",
                    "| Test model | Runs | Gen pass rate | Final pass rate | Avg tests | Avg line cov. | Avg branch cov. | Avg mutation score |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|",
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
                                _percent(model_summary.get("generation_pass_rate")),
                                _percent(model_summary.get("final_pass_rate")),
                                _number(model_summary.get("final_means", {}).get("tests"), 2),
                                _percent(model_summary.get("final_means", {}).get("line_coverage")),
                                _percent(model_summary.get("final_means", {}).get("branch_coverage")),
                                _percent(model_summary.get("final_means", {}).get("mutation_score")),
                            ]
                        )
                        + " |"
                    )
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
