"""Calculate precision only from explicitly completed manual audit cells."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

TRUE_VALUES = {"yes", "y", "true", "1", "correct", "pass"}
FALSE_VALUES = {"no", "n", "false", "0", "incorrect", "fail"}


@dataclass(frozen=True, slots=True)
class PrecisionMetric:
    correct: int
    evaluated: int
    invalid: int = 0

    @property
    def percentage(self) -> float | None:
        return round(100 * self.correct / self.evaluated, 1) if self.evaluated else None


AUDIT_METRICS = {
    "shopify": "manual_shopify_correct",
    "india": "manual_india_correct",
    "logo": "manual_logo_correct",
    "state": "manual_state_correct",
    "contacts": "manual_contacts_correct",
}


def evaluate_audit(path: str | Path) -> dict[str, PrecisionMetric]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[str, PrecisionMetric] = {}
    for name, column in AUDIT_METRICS.items():
        correct = evaluated = invalid = 0
        for row in rows:
            raw = (row.get(column) or "").strip().lower()
            if not raw:
                continue
            if raw in TRUE_VALUES:
                correct += 1
                evaluated += 1
            elif raw in FALSE_VALUES:
                evaluated += 1
            else:
                invalid += 1
        result[name] = PrecisionMetric(correct=correct, evaluated=evaluated, invalid=invalid)
    return result


def format_evaluation(metrics: dict[str, PrecisionMetric]) -> str:
    lines = []
    for name, metric in metrics.items():
        value = f"{metric.percentage:.1f}% ({metric.correct}/{metric.evaluated})" if metric.percentage is not None else "N/A (no completed ratings)"
        suffix = f"; {metric.invalid} invalid value(s) ignored" if metric.invalid else ""
        lines.append(f"{name.title()} precision: {value}{suffix}")
    return "\n".join(lines)

