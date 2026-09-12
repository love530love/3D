"""Conservative model promotion gate; never auto-promotes a challenger.

v1.1 fix: the gate now reads each challenger's OWN log_loss from the
probability report (matched by name) instead of a single hard-coded
`smoothed_position_frequency` anchor. The qualification test also folds in the
BH-FDR corrected p-value from the comparison report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(comparisons: dict, probabilities: dict) -> dict:
    models = probabilities.get("models", {})
    uniform_model = models.get("uniform_baseline") or models.get("uniform") or {}
    uniform_logloss = uniform_model.get("log_loss", float("inf"))
    candidates = []
    for name, result in comparisons.get("comparisons_vs_uniform", {}).items():
        ci = result.get("bootstrap_95ci", [0, 0])
        challenger = models.get(name, {})
        challenger_logloss = challenger.get("log_loss", float("inf"))
        corrected_p = result.get("corrected_p")
        qualifies = bool(
            ci and ci[0] > 0
            and challenger_logloss < uniform_logloss
            and corrected_p is not None and corrected_p < 0.05
        )
        candidates.append({
            "model": name,
            "stable_positive_ci": bool(ci and ci[0] > 0),
            "corrected_p": corrected_p,
            "qualifies_for_review": qualifies,
            "ci": ci,
        })
    qualified = [item["model"] for item in candidates if item["qualifies_for_review"]]
    return {
        "status": "CHALLENGER_REVIEW" if qualified else "BASELINE_REQUIRED",
        "qualified_for_review": qualified,
        "candidates": candidates,
        "automatic_promotion": False,
        "reason": "必须完成专家审计和正式投票后才能改变模型等级。",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="验证 challenger 是否达到专家复核门槛")
    base = Path(__file__).parent
    p.add_argument("--reports", type=Path, default=base / "reports")
    p.add_argument("--out", type=Path, default=base / "reports" / "model-gate-latest.json")
    args = p.parse_args()
    probabilities = json.loads((args.reports / "probability-latest.json").read_text(encoding="utf-8"))
    comparisons = json.loads((args.reports / "model-comparison-latest.json").read_text(encoding="utf-8"))
    result = evaluate(comparisons, probabilities)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Model gate: {result['status']}")
    print(f"Report: {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    main()
