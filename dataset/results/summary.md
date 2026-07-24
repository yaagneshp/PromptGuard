# Evaluation Summary

## Per-category detection (micro-averaged)

| Metric | Baseline (regex-only) | Hybrid |
|---|---|---|
| Precision | 1.0 | 0.9023 |
| Recall | 0.5 | 0.9812 |
| F1 | 0.6667 | 0.9401 |

## Prompt-level: any PII detected at all (raw detection capability)

| Metric | Baseline | Hybrid |
|---|---|---|
| Precision | 1.0 | 0.9586 |
| Recall | 0.5846 | 0.9808 |
| F1 | 0.7379 | 0.9696 |
| False Positive Rate | 0.0 | 0.1019 |

## Prompt-level: flagged at medium-risk threshold (operational alerting)

| Metric | Baseline | Hybrid |
|---|---|---|
| Precision | 1.0 | 1.0 |
| Recall | 0.2769 | 0.4385 |
| F1 | 0.4337 | 0.6096 |
| False Positive Rate | 0.0 | 0.0 |

## Latency (ms per scan)

| Stat | Regex-only | Hybrid |
|---|---|---|
| Mean | 0.067 | 15.501 |
| Median | 0.058 | 14.828 |
| P95 | 0.126 | 19.825 |
| Max | 0.311 | 47.671 |