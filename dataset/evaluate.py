"""Runs the synthetic dataset through both the regex-only baseline (Phase 1)
and the full hybrid pipeline (Phase 3), and computes:

1. Per-category detection metrics (precision/recall/F1), micro-averaged,
   for baseline vs hybrid.
2. Prompt-level "is this prompt sensitive" classification metrics
   (precision/recall/F1/false-positive-rate), baseline vs hybrid, against
   the benign/confidential/policy_violating ground truth label.
3. Per-scan latency, baseline vs hybrid.

Run from the backend's venv: ../backend/venv/Scripts/python evaluate.py
"""

import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.detectors.combined import scan_text_combined  # noqa: E402
from app.detectors.presidio_detector import get_analyzer  # noqa: E402
from app.detectors.regex_detectors import find_regex_matches, resolve_overlaps  # noqa: E402
from app.risk import CATEGORY_WEIGHTS, score_from_matches  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent / "prompts.jsonl"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

RISK_THRESHOLD = 25.0  # matches policy.yaml's "medium" cutoff


def load_dataset() -> list[dict]:
    records = []
    with DATASET_PATH.open(encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    return records


def prf1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def main() -> None:
    print("Warming up Presidio (spaCy model load)...")
    get_analyzer()

    records = load_dataset()
    print(f"Evaluating {len(records)} prompts...")

    category_tp: dict[str, dict[str, int]] = {"baseline": {}, "hybrid": {}}
    category_fp: dict[str, dict[str, int]] = {"baseline": {}, "hybrid": {}}
    category_fn: dict[str, dict[str, int]] = {"baseline": {}, "hybrid": {}}

    prompt_level = {
        "baseline": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
        "hybrid": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
    }
    # Separate from the threshold-gated view above: "any PII detected at
    # all", regardless of severity. Distinguishes raw detection capability
    # from the medium-risk alerting threshold, which deliberately requires
    # accumulated severity before flagging (a single email shouldn't page
    # anyone - that's a policy/alert-fatigue decision, not a detection gap).
    prompt_level_any = {
        "baseline": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
        "hybrid": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
    }

    regex_latencies_ms: list[float] = []
    hybrid_latencies_ms: list[float] = []

    per_prompt_results = []

    for r in records:
        text = r["text"]
        expected = set(r["expected_categories"])
        is_sensitive = r["label"] != "benign"

        # --- Timed hybrid scan (this is also where regex matches come from) ---
        t0 = time.perf_counter()
        scan = scan_text_combined(text)
        t1 = time.perf_counter()
        hybrid_latencies_ms.append((t1 - t0) * 1000)

        risk = score_from_matches(scan.matches, text)

        # --- Timed regex-only pass (isolated, for latency comparison) ---
        t2 = time.perf_counter()
        regex_only_matches = resolve_overlaps(find_regex_matches(text))
        t3 = time.perf_counter()
        regex_latencies_ms.append((t3 - t2) * 1000)

        baseline_categories = {c for c, _, _ in regex_only_matches}
        hybrid_categories = {m.category for m in scan.matches}

        for source, predicted in (("baseline", baseline_categories), ("hybrid", hybrid_categories)):
            all_categories = expected | predicted
            for category in all_categories:
                if category in expected and category in predicted:
                    category_tp[source][category] = category_tp[source].get(category, 0) + 1
                elif category in predicted and category not in expected:
                    category_fp[source][category] = category_fp[source].get(category, 0) + 1
                elif category in expected and category not in predicted:
                    category_fn[source][category] = category_fn[source].get(category, 0) + 1

        baseline_regex_score = sum(CATEGORY_WEIGHTS.get(c, 5) for c in baseline_categories)
        baseline_flagged = baseline_regex_score >= RISK_THRESHOLD
        hybrid_flagged = risk.combined_score >= RISK_THRESHOLD

        baseline_any = len(baseline_categories) > 0
        hybrid_any = len(hybrid_categories) > 0

        for source, flagged in (("baseline", baseline_flagged), ("hybrid", hybrid_flagged)):
            if flagged and is_sensitive:
                prompt_level[source]["tp"] += 1
            elif flagged and not is_sensitive:
                prompt_level[source]["fp"] += 1
            elif not flagged and is_sensitive:
                prompt_level[source]["fn"] += 1
            else:
                prompt_level[source]["tn"] += 1

        for source, flagged in (("baseline", baseline_any), ("hybrid", hybrid_any)):
            if flagged and is_sensitive:
                prompt_level_any[source]["tp"] += 1
            elif flagged and not is_sensitive:
                prompt_level_any[source]["fp"] += 1
            elif not flagged and is_sensitive:
                prompt_level_any[source]["fn"] += 1
            else:
                prompt_level_any[source]["tn"] += 1

        per_prompt_results.append(
            {
                "id": r["id"],
                "label": r["label"],
                "expected_categories": sorted(expected),
                "baseline_categories": sorted(baseline_categories),
                "hybrid_categories": sorted(hybrid_categories),
                "baseline_flagged": baseline_flagged,
                "hybrid_flagged": hybrid_flagged,
                "regex_score": risk.regex_score,
                "presidio_score": risk.presidio_score,
                "contextual_score": risk.contextual_score,
                "combined_score": risk.combined_score,
                "risk_level": risk.risk_level,
            }
        )

    # --- Aggregate per-category metrics (micro-averaged) ---
    category_summary = {}
    for source in ("baseline", "hybrid"):
        total_tp = sum(category_tp[source].values())
        total_fp = sum(category_fp[source].values())
        total_fn = sum(category_fn[source].values())
        precision, recall, f1 = prf1(total_tp, total_fp, total_fn)
        category_summary[source] = {
            "micro_precision": round(precision, 4),
            "micro_recall": round(recall, 4),
            "micro_f1": round(f1, 4),
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
        }

    per_category_detail = {}
    all_cats = set(category_tp["hybrid"]) | set(category_fp["hybrid"]) | set(category_fn["hybrid"])
    for category in sorted(all_cats):
        per_category_detail[category] = {}
        for source in ("baseline", "hybrid"):
            tp = category_tp[source].get(category, 0)
            fp = category_fp[source].get(category, 0)
            fn = category_fn[source].get(category, 0)
            precision, recall, f1 = prf1(tp, fp, fn)
            per_category_detail[category][source] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "tp": tp,
                "fp": fp,
                "fn": fn,
            }

    # --- Aggregate prompt-level metrics ---
    def summarize_prompt_level(counts: dict) -> dict:
        summary = {}
        for source in ("baseline", "hybrid"):
            tp, fp, fn, tn = (
                counts[source]["tp"],
                counts[source]["fp"],
                counts[source]["fn"],
                counts[source]["tn"],
            )
            precision, recall, f1 = prf1(tp, fp, fn)
            fpr = fp / (fp + tn) if (fp + tn) else 0.0
            accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) else 0.0
            summary[source] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "false_positive_rate": round(fpr, 4),
                "accuracy": round(accuracy, 4),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
            }
        return summary

    prompt_summary = summarize_prompt_level(prompt_level)
    prompt_summary_any = summarize_prompt_level(prompt_level_any)

    def latency_stats(values: list[float]) -> dict:
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "mean_ms": round(sum(sorted_vals) / n, 3),
            "median_ms": round(sorted_vals[n // 2], 3),
            "p95_ms": round(sorted_vals[int(n * 0.95)], 3),
            "min_ms": round(sorted_vals[0], 3),
            "max_ms": round(sorted_vals[-1], 3),
        }

    latency_summary = {
        "regex_only": latency_stats(regex_latencies_ms),
        "hybrid": latency_stats(hybrid_latencies_ms),
    }

    (RESULTS_DIR / "category_metrics.json").write_text(
        json.dumps({"summary": category_summary, "per_category": per_category_detail}, indent=2)
    )
    (RESULTS_DIR / "prompt_level_metrics.json").write_text(
        json.dumps({"risk_threshold_flagged": prompt_summary, "any_detection_flagged": prompt_summary_any}, indent=2)
    )
    (RESULTS_DIR / "latency.json").write_text(json.dumps(latency_summary, indent=2))
    with (RESULTS_DIR / "per_prompt_results.jsonl").open("w", encoding="utf-8") as f:
        for row in per_prompt_results:
            f.write(json.dumps(row) + "\n")

    print("\n=== Per-category detection (micro-averaged) ===")
    print(json.dumps(category_summary, indent=2))
    print("\n=== Prompt-level: flagged at medium-risk threshold (>=25) ===")
    print(json.dumps(prompt_summary, indent=2))
    print("\n=== Prompt-level: any PII detected at all (raw detection capability) ===")
    print(json.dumps(prompt_summary_any, indent=2))
    print("\n=== Latency ===")
    print(json.dumps(latency_summary, indent=2))
    print(f"\nResults written to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
