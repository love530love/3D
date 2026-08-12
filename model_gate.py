"""Conservative model promotion gate; never auto-promotes a challenger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="验证 challenger 是否达到专家复核门槛")
    base = Path(__file__).parent
    p.add_argument("--reports", type=Path, default=base / "reports")
    p.add_argument("--out", type=Path, default=base / "reports" / "model-gate-latest.json")
    args = p.parse_args()
    probabilities = json.loads((args.reports / "probability-latest.json").read_text(encoding="utf-8"))
    comparisons = json.loads((args.reports / "model-comparison-latest.json").read_text(encoding="utf-8"))
    uniform = probabilities.get("models", {}).get("uniform", {})
    candidates = []
    for name, result in comparisons.get("comparisons_vs_uniform", {}).items():
        ci = result.get("bootstrap_95ci", [0, 0])
        challenger = probabilities.get("models", {}).get("smoothed_position_frequency", {})
        qualifies = bool(ci and ci[0] > 0 and challenger.get("log_loss", float("inf")) < uniform.get("log_loss", float("inf")))
        candidates.append({"model": name, "stable_positive_ci": bool(ci and ci[0] > 0), "qualifies_for_review": qualifies, "ci": ci})
    qualified = [item["model"] for item in candidates if item["qualifies_for_review"]]
    result = {
        "status": "CHALLENGER_REVIEW" if qualified else "BASELINE_REQUIRED",
        "qualified_for_review": qualified,
        "candidates": candidates,
        "automatic_promotion": False,
        "reason": "必须完成专家审计和正式投票后才能改变模型等级。",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Model gate: {result['status']}")
    print(f"Report: {args.out.resolve()}")


if __name__ == "__main__":
    main()
