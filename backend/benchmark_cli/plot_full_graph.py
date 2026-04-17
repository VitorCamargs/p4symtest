#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from open_pdf_helper import try_open_file


DEFAULT_OUTPUT_PDF = "graph_full.pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate full-pipeline benchmark graph.")
    parser.add_argument("--csv", required=True, help="Path to full_raw.csv")
    parser.add_argument(
        "--output-pdf",
        default=DEFAULT_OUTPUT_PDF,
        help=f"Output PDF file/path (default: {DEFAULT_OUTPUT_PDF})",
    )
    parser.add_argument("--open", action="store_true", help="Try to open the PDF automatically after saving.")
    return parser.parse_args()


def normalize_success(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def main() -> int:
    args = parse_args()
    csv_file = Path(args.csv).resolve()

    if not csv_file.exists():
        print(f"Error: CSV not found: {csv_file}")
        return 1

    try:
        df = pd.read_csv(csv_file)
    except Exception as exc:
        print(f"Error reading CSV: {exc}")
        return 1

    required_cols = {
        "ingress_tables",
        "parser_time_s",
        "ingress_time_s",
        "egress_time_s",
        "deparser_time_s",
        "success",
    }
    missing = required_cols - set(df.columns)
    if missing:
        print(f"Error: missing CSV columns: {sorted(missing)}")
        return 1

    df = df.copy()
    if "run_number" in df.columns:
        df = df[pd.to_numeric(df["run_number"], errors="coerce") > 0]

    df["success_norm"] = normalize_success(df["success"])
    df = df[df["success_norm"]]
    if df.empty:
        print("No successful execution data found to generate the graph.")
        return 1

    numeric_cols = ["ingress_tables", "parser_time_s", "ingress_time_s", "egress_time_s", "deparser_time_s"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=numeric_cols)
    if df.empty:
        print("Insufficient data after normalization.")
        return 1

    agg = (
        df.groupby("ingress_tables")[["parser_time_s", "ingress_time_s", "egress_time_s", "deparser_time_s"]]
        .mean()
        .sort_index()
    )

    x_labels = [str(int(v)) for v in agg.index.tolist()]
    parser_vals = agg["parser_time_s"].tolist()
    ingress_vals = agg["ingress_time_s"].tolist()
    egress_vals = agg["egress_time_s"].tolist()
    deparser_vals = agg["deparser_time_s"].tolist()

    fig, ax = plt.subplots(figsize=(12, 7))

    b1 = ax.bar(x_labels, parser_vals, label="Parser", color="#3498db")
    b2 = ax.bar(x_labels, ingress_vals, bottom=parser_vals, label="Ingress", color="#e67e22")

    stack_2 = [p + i for p, i in zip(parser_vals, ingress_vals)]
    b3 = ax.bar(x_labels, egress_vals, bottom=stack_2, label="Egress", color="#9b59b6")

    stack_3 = [a + b for a, b in zip(stack_2, egress_vals)]
    b4 = ax.bar(x_labels, deparser_vals, bottom=stack_3, label="Deparser", color="#2ecc71")

    _ = (b1, b2, b3, b4)

    ax.set_title("Full Pipeline Average Time by Number of Ingress Tables", fontsize=18)
    ax.set_xlabel("Ingress Tables", fontsize=13)
    ax.set_ylabel("Average Time (s)", fontsize=13)
    ax.legend()
    ax.grid(False)

    print("Opening interactive view... close the window to save the PDF.")
    plt.show()

    output_pdf = Path(args.output_pdf).resolve()
    fig.savefig(output_pdf, format="pdf", bbox_inches="tight")
    print(f"PDF saved to: {output_pdf}")

    if args.open:
        try_open_file(output_pdf)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
