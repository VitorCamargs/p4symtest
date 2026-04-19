#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

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


def format_numeric_label(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


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

    figures: list[plt.Figure] = []
    for pipe in pipelines:
        pipe_df = df[df["pipeline"] == pipe].copy()
        action_values = sorted(pipe_df["actions_per_table"].dropna().unique().tolist())
        if not action_values:
            continue

        n_actions = len(action_values)
        ncols = min(4, n_actions)
        nrows = math.ceil(n_actions / ncols)
        fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, 3.8 * nrows), sharey=True)
        axes_flat = axes.flatten() if hasattr(axes, "flatten") else [axes]

        y_min = float(pipe_df["duration_s"].min())
        y_max = float(pipe_df["duration_s"].max())
        if y_max > y_min:
            pad = (y_max - y_min) * 0.05
            y_limits = (y_min - pad, y_max + pad)
        else:
            y_limits = (max(0.0, y_min - 0.05), y_max + 0.05)

        for idx, action in enumerate(action_values):
            ax = axes_flat[idx]
            action_df = pipe_df[pipe_df["actions_per_table"] == action].copy()
            state_values = sorted(action_df["parser_states"].dropna().unique().tolist())
            if not state_values:
                ax.set_title(f"Actions={int(action)} (no data)")
                ax.axis("off")
                continue

            box_data = [
                action_df[action_df["parser_states"] == state]["duration_s"].tolist()
                for state in state_values
            ]
            tick_labels = [format_numeric_label(state) for state in state_values]

            bp = ax.boxplot(box_data, labels=tick_labels, patch_artist=True)
            for box in bp["boxes"]:
                box.set_facecolor("#4C78A8")
                box.set_edgecolor("black")
            for median in bp["medians"]:
                median.set_color("black")
                median.set_linewidth(1.6)

            ax.set_title(f"Actions per Table = {format_numeric_label(action)}", fontsize=11)
            ax.set_xlabel("Parser States", fontsize=10)
            if idx % ncols == 0:
                ax.set_ylabel("Table Time (s)", fontsize=10)
            ax.set_ylim(y_limits)
            ax.grid(True, axis="y", linestyle="--", linewidth=0.5, alpha=0.5)

        for idx in range(len(action_values), len(axes_flat)):
            ax = axes_flat[idx]
            ax.axis("off")

        fig.suptitle(
            f"{pipeline_label(pipe)}: Time vs Parser States per Actions (Boxplots)",
            fontsize=15,
        )
        plt.tight_layout(rect=[0, 0, 1, 0.95])
        figures.append(fig)

    if not figures:
        print("No valid data available for plotting after filtering.")
        return 1

    output_pdf = Path(args.output_pdf).resolve()
    if len(figures) == 1:
        figures[0].savefig(output_pdf, format="pdf", bbox_inches="tight")
    else:
        with PdfPages(output_pdf) as pdf:
            for fig in figures:
                pdf.savefig(fig, bbox_inches="tight")

    if os.environ.get("DISPLAY"):
        print("Opening interactive view... close the windows when done.")
        plt.show()
    else:
        print("No DISPLAY detected; saving PDF without interactive preview.")

    print(f"PDF saved to: {output_pdf}")

    if args.open:
        try_open_file(output_pdf)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
