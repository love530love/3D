"""Auditable evidence synthesizer: a bounded 'brain', not self-modifying code."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    p = argparse.ArgumentParser(description="汇总福彩3D全部分析模块并生成综合判断")
    base = Path(__file__).parent
    p.add_argument("--reports", type=Path, default=base / "reports")
    p.add_argument("--out", type=Path, default=base / "reports" / "brain-decision-latest.json")
    args = p.parse_args()
    quality = read(args.reports / "quality-latest.json")
    randomness = read(args.reports / "randomness-latest.json")
    models = read(args.reports / "models-latest.json")
    probabilities = read(args.reports / "probability-latest.json")
    comparison = read(args.reports / "model-comparison-latest.json")
    drift = read(args.reports / "drift-latest.json")
    outcomes = read(args.reports / "outcomes-latest.json")
    quality_pass = quality.get("status") == "PASS"
    probability_models = probabilities.get("models", {})
    ranked = sorted(probability_models.items(), key=lambda item: item[1].get("log_loss", float("inf")))
    best_model = ranked[0][0] if ranked else "uniform"
    challenger_advantage = {}
    for name, result in comparison.get("comparisons_vs_uniform", {}).items():
        interval = result.get("bootstrap_95ci", [0, 0])
        challenger_advantage[name] = {"difference": result.get("observed_rate_difference"), "ci": interval,
                                      "stable_positive": interval[0] > 0}
    if not quality_pass:
        verdict = "FROZEN_DATA_QUALITY_FAILURE"
        recommendation = "停止模型结论和预测发布，先修复质量门禁。"
    elif any(item[1].get("stable_positive") for item in challenger_advantage.items()):
        verdict = "CHALLENGER_REVIEW_REQUIRED"
        recommendation = "存在需要专家复核的历史差异，但尚不足以证明可预测性。"
    else:
        verdict = "NO_STABLE_PREDICTIVE_EDGE_OBSERVED"
        recommendation = "保留透明基线；当前证据未显示稳定超过随机基线的优势。"
    decision = {
        "brain_version": "evidence-brain-v1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": verdict,
        "recommendation": recommendation,
        "selected_for_experiment_only": best_model,
        "quality_gate": quality,
        "randomness_summary": randomness,
        "model_summary": models,
        "probability_summary": probabilities,
        "challenger_comparison": challenger_advantage,
        "outcome_archive": outcomes,
        "drift_summary": drift,
        "evolution_policy": {
            "auto_modify_code": False,
            "auto_delete_data": False,
            "requires_expert_audit_for_model_change": True,
            "next_proposals": [
                "累积更多冻结预测盲评样本",
                "按模型版本分析滚动校准和漂移",
                "若引入新模型，先提交 MODEL_PROPOSAL_TEMPLATE.md",
            ],
        },
        "disclaimer": "这是多模块证据汇总，不是数字意识，也不保证或承诺彩票可预测。",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evidence brain verdict: {verdict}")
    print(f"Experiment-only selected model: {best_model}")
    print(f"Decision: {args.out.resolve()}")


if __name__ == "__main__":
    main()
