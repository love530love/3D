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
        lines.append(
            f"- {name}: 差异 {item.get('observed_rate_difference', 'N/A')}，"
            f"95% CI {item.get('bootstrap_95ci', 'N/A')}，"
            f"校正后 p={item.get('corrected_p', 'N/A')}"
        )
    lines += ["", "## 中枢判断", "", f"- 综合 verdict：`{brain.get('verdict', 'N/A')}`", f"- 模型门禁：`{gate.get('status', 'N/A')}`", f"- 实验性模型：`{brain.get('selected_for_experiment_only', 'N/A')}`", "", "模型门禁不等于模型晋升；任何升级仍需专家审计和投票。"]
    lines += ["", "## 方法限制", "", "短期频率、显著性和命中都可能来自随机波动；后续运行必须继续使用时间冻结、随机基线和盲评。", "",
              "## 结论的认识论边界", "",
              "本实验结论是**负向的**：在覆盖多家族方法（频率 / Laplace 平滑 / 近期窗口 / 一阶马尔可夫）、严格时间冻结、Bootstrap 与 Benjamini–Hochberg 多重比较校正下，一致**未观测到**稳定优于随机基线的优势。",
              "这构成“反对可预测性的强证据”，而**不是**“彩票在原理上不可预测”的正向证明——后者在逻辑上无法由任何有限经验证据达成。",
              "残余不确定性：未覆盖深度学习 / 树模型 / 外生特征；逐位预测未对和值、形态等池化目标独立验证；马尔可夫仅一阶；样本约数千期，极低频结构可能低于检测灵敏度。", ""]
    text = "\n".join(lines)
    # Guard against any "proven unpredictable" positive-proof phrasing leaking in.
    forbidden = ["证明不可预测", "已证明无法预测", "证明彩票不可预测"]
    for phrase in forbidden:
        if phrase in text:
            print(f"[teaching-report] FORBIDDEN phrase detected: {phrase}", file=sys.stderr)
            return 1
    output = args.reports / "teaching-latest.md"
    output.write_text(text, encoding="utf-8")
    print(f"Teaching report: {output.resolve()}")


if __name__ == "__main__":
    main()
