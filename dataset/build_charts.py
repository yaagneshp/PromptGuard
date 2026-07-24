"""Builds static PNG charts and a markdown summary table from evaluate.py's
output, for the dissertation's evaluation chapter. Run after evaluate.py.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).resolve().parent / "results"

BASELINE_COLOR = "#2a78d6"  # categorical slot 1 (blue)
HYBRID_COLOR = "#eb6834"  # categorical slot 2 (orange)


def load(name: str) -> dict:
    return json.loads((RESULTS_DIR / name).read_text())


def grouped_bar(categories, baseline_vals, hybrid_vals, ylabel, title, out_name, ylim=None, log=False):
    x = range(len(categories))
    width = 0.35
    fig, ax = plt.subplots(figsize=(max(6, len(categories) * 0.9), 5))
    ax.bar([i - width / 2 for i in x], baseline_vals, width, label="Regex-only (baseline)", color=BASELINE_COLOR)
    ax.bar([i + width / 2 for i in x], hybrid_vals, width, label="Hybrid (regex+Presidio+context)", color=HYBRID_COLOR)
    ax.set_xticks(list(x))
    ax.set_xticklabels(categories, rotation=30, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if ylim:
        ax.set_ylim(*ylim)
    if log:
        ax.set_yscale("log")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / out_name, dpi=150)
    plt.close(fig)
    print(f"Wrote {out_name}")


def main() -> None:
    category_metrics = load("category_metrics.json")
    prompt_metrics = load("prompt_level_metrics.json")
    latency = load("latency.json")

    # --- Per-category F1 ---
    per_cat = category_metrics["per_category"]
    cats = sorted(per_cat.keys())
    baseline_f1 = [per_cat[c]["baseline"]["f1"] for c in cats]
    hybrid_f1 = [per_cat[c]["hybrid"]["f1"] for c in cats]
    grouped_bar(
        cats, baseline_f1, hybrid_f1, "F1 score", "Per-category detection F1: baseline vs hybrid",
        "chart_per_category_f1.png", ylim=(0, 1.05),
    )

    # --- Micro-averaged overall detection metrics ---
    summary = category_metrics["summary"]
    metrics = ["micro_precision", "micro_recall", "micro_f1"]
    labels = ["Precision", "Recall", "F1"]
    grouped_bar(
        labels,
        [summary["baseline"][m] for m in metrics],
        [summary["hybrid"][m] for m in metrics],
        "Score", "Overall per-category detection: baseline vs hybrid",
        "chart_overall_detection.png", ylim=(0, 1.05),
    )

    # --- Prompt-level: any-detection view (raw detection capability) ---
    any_flagged = prompt_metrics["any_detection_flagged"]
    metrics2 = ["precision", "recall", "f1", "false_positive_rate"]
    labels2 = ["Precision", "Recall", "F1", "False Positive Rate"]
    grouped_bar(
        labels2,
        [any_flagged["baseline"][m] for m in metrics2],
        [any_flagged["hybrid"][m] for m in metrics2],
        "Score", "Prompt-level (any PII detected): baseline vs hybrid",
        "chart_prompt_level_any_detection.png", ylim=(0, 1.05),
    )

    # --- Prompt-level: risk-threshold view (operational alerting) ---
    threshold_flagged = prompt_metrics["risk_threshold_flagged"]
    grouped_bar(
        labels2,
        [threshold_flagged["baseline"][m] for m in metrics2],
        [threshold_flagged["hybrid"][m] for m in metrics2],
        "Score", "Prompt-level (flagged at medium-risk threshold): baseline vs hybrid",
        "chart_prompt_level_risk_threshold.png", ylim=(0, 1.05),
    )

    # --- Latency ---
    grouped_bar(
        ["Mean", "Median", "P95"],
        [latency["regex_only"]["mean_ms"], latency["regex_only"]["median_ms"], latency["regex_only"]["p95_ms"]],
        [latency["hybrid"]["mean_ms"], latency["hybrid"]["median_ms"], latency["hybrid"]["p95_ms"]],
        "Latency (ms, log scale)", "Per-scan latency: regex-only vs hybrid",
        "chart_latency.png", log=True,
    )

    # --- Markdown summary table ---
    lines = [
        "# Evaluation Summary\n",
        "## Per-category detection (micro-averaged)\n",
        "| Metric | Baseline (regex-only) | Hybrid |",
        "|---|---|---|",
        f"| Precision | {summary['baseline']['micro_precision']} | {summary['hybrid']['micro_precision']} |",
        f"| Recall | {summary['baseline']['micro_recall']} | {summary['hybrid']['micro_recall']} |",
        f"| F1 | {summary['baseline']['micro_f1']} | {summary['hybrid']['micro_f1']} |",
        "",
        "## Prompt-level: any PII detected at all (raw detection capability)\n",
        "| Metric | Baseline | Hybrid |",
        "|---|---|---|",
        f"| Precision | {any_flagged['baseline']['precision']} | {any_flagged['hybrid']['precision']} |",
        f"| Recall | {any_flagged['baseline']['recall']} | {any_flagged['hybrid']['recall']} |",
        f"| F1 | {any_flagged['baseline']['f1']} | {any_flagged['hybrid']['f1']} |",
        f"| False Positive Rate | {any_flagged['baseline']['false_positive_rate']} | {any_flagged['hybrid']['false_positive_rate']} |",
        "",
        "## Prompt-level: flagged at medium-risk threshold (operational alerting)\n",
        "| Metric | Baseline | Hybrid |",
        "|---|---|---|",
        f"| Precision | {threshold_flagged['baseline']['precision']} | {threshold_flagged['hybrid']['precision']} |",
        f"| Recall | {threshold_flagged['baseline']['recall']} | {threshold_flagged['hybrid']['recall']} |",
        f"| F1 | {threshold_flagged['baseline']['f1']} | {threshold_flagged['hybrid']['f1']} |",
        f"| False Positive Rate | {threshold_flagged['baseline']['false_positive_rate']} | {threshold_flagged['hybrid']['false_positive_rate']} |",
        "",
        "## Latency (ms per scan)\n",
        "| Stat | Regex-only | Hybrid |",
        "|---|---|---|",
        f"| Mean | {latency['regex_only']['mean_ms']} | {latency['hybrid']['mean_ms']} |",
        f"| Median | {latency['regex_only']['median_ms']} | {latency['hybrid']['median_ms']} |",
        f"| P95 | {latency['regex_only']['p95_ms']} | {latency['hybrid']['p95_ms']} |",
        f"| Max | {latency['regex_only']['max_ms']} | {latency['hybrid']['max_ms']} |",
    ]
    (RESULTS_DIR / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote summary.md")


if __name__ == "__main__":
    main()
