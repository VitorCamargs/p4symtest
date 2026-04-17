#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from open_pdf_helper import try_open_file


DEFAULT_OUTPUT_PDF = "graph_parser.pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate parser benchmark graph from raw CSV.")
    parser.add_argument("--csv", required=True, help="Path to parser_raw.csv")
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

    required_cols = {"parser_states", "duration_s", "success"}
    missing = required_cols - set(df.columns)
    if missing:
        print(f"Error: missing CSV columns: {sorted(missing)}")
        return 1

    df = df.copy()
    df["success_norm"] = normalize_success(df["success"])
    if "run_number" in df.columns:
        df = df[pd.to_numeric(df["run_number"], errors="coerce") > 0]

    df = df[df["success_norm"]]
    if df.empty:
        print("No successful execution data found to generate the graph.")
        return 1

    df["parser_states"] = pd.to_numeric(df["parser_states"], errors="coerce")
    df["duration_s"] = pd.to_numeric(df["duration_s"], errors="coerce")
    df = df.dropna(subset=["parser_states", "duration_s"]) 

    if df.empty:
        print("Insufficient data after normalization.")
        return 1

    grouped = df.groupby("parser_states")
    ordered_states = sorted(grouped.groups.keys())
    data = [grouped.get_group(state)["duration_s"].tolist() for state in ordered_states]

    fig, ax = plt.subplots(figsize=(11, 7))
    bp = ax.boxplot(
        data,
        patch_artist=True,
        labels=[str(int(s)) for s in ordered_states],
    )

    for box in bp["boxes"]:
        box.set_facecolor("#3498db")
        box.set_edgecolor("black")
    for median in bp["medians"]:
        median.set_color("black")
        median.set_linewidth(1.8)

    ax.set_title("Parser Execution Time vs. Parser States", fontsize=20)
    ax.set_xlabel("Number of Parser States", fontsize=14)
    ax.set_ylabel("Parser Time (s)", fontsize=14)
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
