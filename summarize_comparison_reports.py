from __future__ import annotations

"""Aggregate comparison reports across benchmark runs."""

import argparse
from pathlib import Path

from benchmark_pipeline.report_summary import (
    find_comparison_reports,
    format_summary_markdown,
    load_comparison_reports,
    summarize_report_payloads,
    write_summary_files,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate comparison_report.json files across benchmark runs.")
    parser.add_argument(
        "--reports-root",
        default="artifacts/runs",
        help="Root directory containing preserved run artifacts.",
    )
    parser.add_argument(
        "--output-json",
        default="artifacts/summary/comparison_reports_summary.json",
        help="Path for the aggregated JSON summary.",
    )
    parser.add_argument(
        "--output-md",
        default="artifacts/summary/comparison_reports_summary.md",
        help="Path for the aggregated Markdown summary.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    reports_root = Path(args.reports_root)
    report_paths = find_comparison_reports(reports_root)
    if not report_paths:
        raise FileNotFoundError(f"No comparison_report.json files found under {reports_root}")

    payloads = load_comparison_reports(reports_root)
    summary = summarize_report_payloads(payloads)
    write_summary_files(
        summary,
        output_json=Path(args.output_json) if args.output_json else None,
        output_md=Path(args.output_md) if args.output_md else None,
    )

    print()
    print("=" * 72)
    print("[summary] Aggregated comparison reports")
    print(f"[summary] Reports found: {len(report_paths)}")
    print(f"[summary] Reports root: {reports_root.resolve()}")
    if args.output_json:
        print(f"[summary] JSON summary: {Path(args.output_json).resolve()}")
    if args.output_md:
        print(f"[summary] Markdown summary: {Path(args.output_md).resolve()}")
    print("=" * 72)
    print()
    print(format_summary_markdown(summary))


if __name__ == "__main__":
    main()
