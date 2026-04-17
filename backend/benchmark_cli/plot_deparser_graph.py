#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from open_pdf_helper import try_open_file


DEFAULT_OUTPUT_PDF = "graph_deparser.pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deparser benchmark graph from raw CSV.")
    parser.add_argument("--csv", required=True, help="Path to deparser_raw.csv")
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
    if "run_number" in df.columns:
        df = df[pd.to_numeric(df["run_number"], errors="coerce") > 0]

    df["success_norm"] = normalize_success(df["success"])
    df = df[df["success_norm"]]

    if df.empty:
        print("No successful execution data found to generate the graph.")
        return 1

    df["parser_states"] = pd.to_numeric(df["parser_states"], errors="coerce")
    df["duration_s"] = pd.to_numeric(df["duration_s"], errors="coerce")
    if "output_states" in df.columns:
        df["output_states"] = pd.to_numeric(df["output_states"], errors="coerce")

    df = df.dropna(subset=["parser_states", "duration_s"])
    if df.empty:
        print("Insufficient data after normalization.")
        return 1

    grouped = df.groupby("parser_states")
    ordered_states = sorted(grouped.groups.keys())
    duration_data = [grouped.get_group(state)["duration_s"].tolist() for state in ordered_states]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    bp = ax1.boxplot(
        duration_data,
        patch_artist=True,
        labels=[str(int(s)) for s in ordered_states],
    )
    for box in bp["boxes"]:
        box.set_facecolor("#3498db")
        box.set_edgecolor("black")
    for median in bp["medians"]:
        median.set_color("black")
        median.set_linewidth(1.8)

    ax1.set_title("Deparser Time vs. Parser States", fontsize=16)
    ax1.set_xlabel("Number of Parser States", fontsize=12)
    ax1.set_ylabel("Deparser Time (s)", fontsize=12)
    ax1.grid(False)

    if "output_states" in df.columns and df["output_states"].notna().any():
        avg_out = df.groupby("parser_states")["output_states"].mean().reindex(ordered_states)
        ax2.plot(
            [int(s) for s in ordered_states],
            avg_out.tolist(),
            marker="o",
            linewidth=2,
            color="#e74c3c",
        )
        ax2.set_title("Average Deparser Output States", fontsize=16)
        ax2.set_xlabel("Number of Parser States", fontsize=12)
        ax2.set_ylabel("Output States", fontsize=12)
        ax2.grid(False)
    else:
        ax2.axis("off")
        ax2.text(0.5, 0.5, "No output_states column in CSV", ha="center", va="center", fontsize=12)

    fig.suptitle("Deparser Benchmark Analysis", fontsize=20)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

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
