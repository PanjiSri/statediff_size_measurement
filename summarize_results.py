from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator, ScalarFormatter
except ImportError:
    plt = None
    MaxNLocator = None
    ScalarFormatter = None

ALLOWED_MODES = {
    "no_optimization",
    "plus_compression",
    "plus_prune",
    "plus_write_coalescing"
}

def percentile(sorted_values: List[int], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * pct
    lower = math.floor(k)
    upper = math.ceil(k)
    if lower == upper:
        return float(sorted_values[int(k)])
    frac = k - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


def compute_stats(values: List[int]) -> Dict[str, float]:
    if not values:
        return {}
    values_sorted = sorted(values)
    mean = sum(values_sorted) / len(values_sorted)
    return {
        "count": len(values_sorted),
        "min": values_sorted[0],
        "median": values_sorted[len(values_sorted) // 2]
        if len(values_sorted) % 2
        else (values_sorted[len(values_sorted) // 2 - 1] + values_sorted[len(values_sorted) // 2]) / 2,
        "p95": percentile(values_sorted, 0.95),
        "max": values_sorted[-1],
        "mean": mean,
    }


def parse_backend(path: Path) -> str:
    stem = path.stem
    prefix = "bookcatalog_results_"
    if stem.startswith(prefix):
        remainder = stem[len(prefix) :]
        return remainder.split("_", 1)[0]
    return "unknown"


def parse_mode(path: Path) -> str:
    parent = path.parent.name
    if parent.startswith("results_"):
        return parent.replace("results_", "")
    if parent == "results":
        return "baseline"
    return parent


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def drop_first_cycle(rows: List[Dict[str, str]], cycle_size: int) -> List[Dict[str, str]]:
    if len(rows) <= cycle_size:
        return []
    return rows[cycle_size:]


def summarize_file(path: Path, cycle_size: int) -> Dict:
    rows = load_rows(path)
    trimmed = drop_first_cycle(rows, cycle_size)

    statediff_vals = [int(r["statediff_size"]) for r in trimmed if r.get("statediff_size")]
    body_vals = [int(r["body_size"]) for r in trimmed if r.get("body_size")]

    methods = Counter(r.get("method", "") for r in trimmed)
    statuses = Counter(r.get("backend_status", "") for r in trimmed)

    return {
        "file": str(path),
        "mode": parse_mode(path),
        "backend": parse_backend(path),
        "rows_total": len(rows),
        "rows_after_drop": len(trimmed),
        "statediff_stats": compute_stats(statediff_vals),
        "body_stats": compute_stats(body_vals),
        "methods": methods,
        "statuses": statuses,
    }


def collect_values_for_aggregation(files: List[Dict], cycle_size: int) -> Dict[Tuple[str, str], List[int]]:
    buckets: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for summary in files:
        if summary["mode"] not in ALLOWED_MODES:
            continue
            
        path = Path(summary["file"])
        rows = load_rows(path)
        trimmed = drop_first_cycle(rows, cycle_size)
        buckets[(summary["mode"], summary["backend"])].extend(
            [int(r["statediff_size"]) for r in trimmed if r.get("statediff_size")]
        )
    return buckets


def main():
    parser = argparse.ArgumentParser(description="Summarize statediff CSVs for plotting.")
    parser.add_argument(
        "--root",
        default=".",
        help="Root directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--cycle-size",
        type=int,
        default=4,
        help="Number of rows to drop per file as the first CRUD cycle (default: 4).",
    )
    parser.add_argument(
        "--plot-dir",
        dest="plot_dir",
        default="results",
        help="Directory to save the plots (default: results/).",
    )
    parser.add_argument(
        "--out-json",
        dest="out_json",
        help="Optional path to write aggregated stats as JSON.",
    )
    parser.add_argument(
        "--log-scale",
        dest="log_scale",
        action="store_true",
        help="Use log scale for Y axis (default: disabled).",
    )
    args = parser.parse_args()

    root = Path(args.root)
    csv_paths = [
        p
        for p in root.glob("results*/*.csv")
        if p.is_file()
    ]
    if not csv_paths:
        print("No CSV files found under results*/")
        return

    file_summaries = [summarize_file(path, args.cycle_size) for path in sorted(csv_paths)]

    agg_buckets = collect_values_for_aggregation(file_summaries, args.cycle_size)
    
    if not agg_buckets:
        print("No data found matching the allowed modes.")
        return

    aggregated = [
        {
            "mode": mode,
            "backend": backend,
            "sample_count": len(values),
            "statediff_stats": compute_stats(values),
        }
        for (mode, backend), values in sorted(agg_buckets.items())
    ]

    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"aggregated": aggregated, "files": file_summaries}
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote JSON summary to {out_path}")

    print("Per-file summaries (after drop):")
    for summary in file_summaries:
        if summary["mode"] in ALLOWED_MODES:
            print(
                f"- {summary['file']}: mode={summary['mode']}, backend={summary['backend']}, "
                f"rows_after_drop={summary['rows_after_drop']}, "
                f"statediff_median={summary['statediff_stats'].get('median','n/a')}, "
                f"p95={summary['statediff_stats'].get('p95','n/a')}, "
                f"max={summary['statediff_stats'].get('max','n/a')}"
            )

    print("\nAggregated by mode/backend (Filtered):")
    for summary in aggregated:
        stats = summary["statediff_stats"]
        print(
            f"- mode={summary['mode']}, backend={summary['backend']}, samples={summary['sample_count']}, "
            f"median={stats.get('median','n/a')}, p95={stats.get('p95','n/a')}, mean={stats.get('mean','n/a')}"
        )

    plot_dir = Path(args.plot_dir)
    create_single_metric_plot(aggregated, plot_dir / "statediff_median.png", "median", log_scale=args.log_scale)
    create_single_metric_plot(aggregated, plot_dir / "statediff_average.png", "mean", log_scale=args.log_scale)
    create_single_metric_plot(aggregated, plot_dir / "statediff_p95.png", "p95", log_scale=args.log_scale)


def create_single_metric_plot(aggregated: List[Dict], output_path: Path, metric: str, log_scale: bool = False) -> None:
    if plt is None or MaxNLocator is None or ScalarFormatter is None:
        print("matplotlib is not installed; skipping plot generation.")
        return

    if not aggregated:
        print(f"No aggregated data to plot for {metric}.")
        return

    backends = sorted({a["backend"] for a in aggregated})
    
    preferred_order = [
        "no_optimization",
        "plus_write_coalescing",
        "plus_prune",
        "plus_compression",
    ]
    
    modes_found = {a["mode"] for a in aggregated}
    modes = [m for m in preferred_order if m in modes_found]

    lookup = {
        (a["mode"], a["backend"]): a["statediff_stats"] for a in aggregated
    }

    fig, ax = plt.subplots(figsize=(10, 6))

    width = 0.8 / max(len(modes), 1)
    
    max_height = 0

    for idx_mode, mode in enumerate(modes):
        offsets = []
        heights = []
        for idx_backend, backend in enumerate(backends):
            x = idx_backend + (idx_mode - (len(modes) - 1) / 2) * width
            stats = lookup.get((mode, backend), {})
            value = stats.get(metric, 0) or 0
            offsets.append(x)
            heights.append(value)
            if value > max_height:
                max_height = value
        
        rects = ax.bar(offsets, heights, width=width, label=mode.replace("_", " "))
        
        for rect in rects:
            height = rect.get_height()
            if height > 0:
                ax.text(
                    rect.get_x() + rect.get_width() / 2, 
                    height, 
                    f'{int(height)}', 
                    ha='center', 
                    va='bottom', 
                    fontsize=8,
                    color='black'
                )

    metric_title = "Average" if metric == "mean" else metric.upper()
    
    ax.set_title(f"{metric_title} Statediff Size (Bytes)")
    ax.set_xticks(range(len(backends)))
    ax.set_xticklabels(backends, rotation=15)
    ax.set_ylabel("Bytes")
    ax.grid(True, which="both", axis="y", linestyle="--", alpha=0.5)
    
    if log_scale:
        ax.set_yscale("log")
        formatter = ScalarFormatter()
        formatter.set_scientific(False)
        ax.yaxis.set_major_formatter(formatter)
    else:
        formatter = ScalarFormatter()
        formatter.set_scientific(False)
        formatter.set_useOffset(False)
        ax.yaxis.set_major_formatter(formatter)
        
        ax.yaxis.set_major_locator(MaxNLocator(nbins=8, steps=[2.5, 5, 10], integer=True))
        
        ax.set_ylim(0, max_height * 1.1) 

    ax.legend(title="Mode", fontsize="small")
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    print(f"Wrote plot to {output_path}")
    plt.close(fig)

if __name__ == "__main__":
    main()
