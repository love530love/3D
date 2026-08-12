"""Assemble current JSON artifacts into a concise human-readable report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    p = argparse.ArgumentParser(description="生成福彩3D统计学习教学报告")
    base = Path(__file__).parent
    p.add_argument("--reports", type=Path, default=base / "reports")
    args = p.parse_args()
    quality = read(args.reports / "quality-latest.json")
    randomness = read(args.reports / "randomness-latest.json")
    models = read(args.reports / "models-latest.json")
    probabilities = read(args.reports / "probability-latest.json")
    comparison = read(args.reports / "model-comparison-latest.json")
    gate = read(args.reports / "model-gate-latest.json")
    brain = read(args.reports / "brain-decision-latest.json")
    lines = ["# 福彩3D统计学习实验报告", "", f"生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}", "",
             "> 本报告用于学习数据工程、统计推断和模型评估，不构成投注建议，也不证明彩票可预测。", ""]
    db = quality.get("database", {})
    lines += ["## 数据质量", "", f"- 期数：{db.get('row_count', 'N/A')}", f"- 范围：{db.get('first_period', 'N/A')} - {db.get('last_period', 'N/A')}", f"- 质量状态：{quality.get('status', 'N/A')}", ""]
    lines += ["## 随机性诊断", "", f"- 数字均匀性近似 p 值：{randomness.get('digit_uniformity', {}).get('p_value_approx', 'N/A')}", f"- 和值滞后相关：{randomness.get('lag1_sum_correlation', 'N/A')}", f"- 置换峰值 p 值：{randomness.get('permutation_peak_test', {}).get('p_value', 'N/A')}", "", "诊断结果不能直接转换为下一期预测。", ""]
    lines += ["## 模型概率评分", "", "| 模型 | Brier | Log Loss | Top-1 |", "|---|---:|---:|---:|"]
    for name, score in probabilities.get("models", {}).items():
        lines.append(f"| {name} | {score.get('brier_score', 'N/A')} | {score.get('log_loss', 'N/A')} | {score.get('top1_rate', 'N/A')} |")
    lines += ["", "## Challenger 差异", "", "Bootstrap 区间跨过 0 时，不应声称存在稳定优势。", ""]
    for name, item in comparison.get("comparisons_vs_uniform", {}).items():
        lines.append(f"- {name}: 差异 {item.get('observed_rate_difference', 'N/A')}，95% CI {item.get('bootstrap_95ci', 'N/A')}")
    lines += ["", "## 中枢判断", "", f"- 综合 verdict：`{brain.get('verdict', 'N/A')}`", f"- 模型门禁：`{gate.get('status', 'N/A')}`", f"- 实验性模型：`{brain.get('selected_for_experiment_only', 'N/A')}`", "", "模型门禁不等于模型晋升；任何升级仍需专家审计和投票。"]
    lines += ["", "## 方法限制", "", "短期频率、显著性和命中都可能来自随机波动；后续运行必须继续使用时间冻结、随机基线和盲评。", ""]
    output = args.reports / "teaching-latest.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Teaching report: {output.resolve()}")


if __name__ == "__main__":
    main()
