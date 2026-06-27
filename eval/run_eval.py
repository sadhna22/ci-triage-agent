"""Batch eval: triage every labeled failure, report per-class accuracy.

Run: `python -m eval.run_eval`

This is the mic-drop — "I built AND evaluated a system." Reports per-class
accuracy so failure modes are visible, not hidden behind one number.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from agent.loop import triage

LABELS_PATH = os.path.join(os.path.dirname(__file__), "labels.json")


def load_labels() -> dict[str, str]:
    with open(LABELS_PATH) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def main() -> None:
    labels = load_labels()
    per_class_total: dict[str, int] = defaultdict(int)
    per_class_correct: dict[str, int] = defaultdict(int)
    misses = []

    for test_id, truth in labels.items():
        verdict = triage(test_id)
        predicted = verdict["verdict"]
        per_class_total[truth] += 1
        if predicted == truth:
            per_class_correct[truth] += 1
        else:
            misses.append((test_id, truth, predicted))

    print("\nPer-class accuracy")
    print("-" * 40)
    total = correct = 0
    for cls in ("FLAKY", "REAL_REGRESSION", "ENVIRONMENT"):
        t, c = per_class_total[cls], per_class_correct[cls]
        total += t
        correct += c
        if t:
            print(f"  {cls:16} {c}/{t}  ({c / t:.0%})")
    print("-" * 40)
    print(f"  {'OVERALL':16} {correct}/{total}  ({correct / total:.0%})")

    if misses:
        print("\nMisses (be ready to explain these — honesty reads as rigor):")
        for test_id, truth, pred in misses:
            print(f"  {test_id}: expected {truth}, got {pred}")


if __name__ == "__main__":
    main()
