#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from open_pdf_helper import try_open_file


DEFAULT_OUTPUT_PDF = "graph_tables.pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate table benchmark graph (ingress/egress).")
    parser.add_argument("--csv", required=True, help="Path to tables_raw.csv")
    parser.add_argument(
        "--output-pdf",
        default=DEFAULT_OUTPUT_PDF,
        help=f"Output PDF file/path (default: {DEFAULT_OUTPUT_PDF})",
    )
    parser.add_argument("--open", action="store_true", help="Try to open the PDF automatically after saving.")
    return parser.parse_args()


def normalize_success(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def pipeline_label(value: str) -> str:
    val = str(value).strip().lower()
    if val == "ingress":
        return "Ingress"
    if val == "egress":
        return "Egress"
    return str(value)


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

    required_cols = {"pipeline", "parser_states", "actions_per_table", "duration_s", "success"}
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

    df["pipeline"] = df["pipeline"].astype(str).str.strip().str.lower()
    df["parser_states"] = pd.to_numeric(df["parser_states"], errors="coerce")
    df["actions_per_table"] = pd.to_numeric(df["actions_per_table"], errors="coerce")
    df["duration_s"] = pd.to_numeric(df["duration_s"], errors="coerce")
    df = df.dropna(subset=["pipeline", "parser_states", "actions_per_table", "duration_s"])

    pipelines = sorted(df["pipeline"].unique().tolist())
    if not pipelines:
        print("No valid pipeline found in CSV.")
        return 1

    fig, axes = plt.subplots(1, len(pipelines), figsize=(9 * len(pipelines), 7), sharey=True)
    if len(pipelines) == 1:
        axes = [axes]

    for ax, pipe in zip(axes, pipelines):
        pipe_df = df[df["pipeline"] == pipe].copy()
        pipe_df["cfg"] = (
            pipe_df["parser_states"].astype(int).astype(str)
            + "S/"
            + pipe_df["actions_per_table"].astype(int).astype(str)
            + "A"
        )
        order = (
            pipe_df[["parser_states", "actions_per_table", "cfg"]]
            .drop_duplicates()
            .sort_values(["parser_states", "actions_per_table"])["cfg"]
            .tolist()
        )

        data = [pipe_df[pipe_df["cfg"] == cfg]["duration_s"].tolist() for cfg in order]

        bp = ax.boxplot(data, patch_artist=True, labels=order)
        for box in bp["boxes"]:
            box.set_facecolor("#3498db")
            box.set_edgecolor("black")
        for median in bp["medians"]:
            median.set_color("black")
            median.set_linewidth(1.8)

        ax.set_title(f"{pipeline_label(pipe)} Table Time", fontsize=16)
        ax.set_xlabel("States (S) / Actions (A)", fontsize=12)
        ax.tick_params(axis="x", rotation=45, labelsize=10)
        ax.grid(False)

    axes[0].set_ylabel("Table Time (s)", fontsize=12)
    fig.suptitle("Table Benchmark Time Distribution", fontsize=20)
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
