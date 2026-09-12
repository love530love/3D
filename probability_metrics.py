"""Probability scoring and calibration for position-wise lottery models."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path

from models_sd3d import REGISTRY


def load(db: Path) -> list[str]:
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT values_json FROM draws ORDER BY CAST(period AS INTEGER)").fetchall()
    result = []
    for (payload,) in rows:
        fields = json.loads(payload)
        number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(number) == 3:
            result.append(number)
    return result


def score_with_distribution(distribution, draws: list[str], min_train: int, alpha: float) -> dict:
    brier = 0.0
    log_loss = 0.0
    calibration = [0.0] * 10
    calibration_n = [0] * 10
    tested = 0
    for index in range(min_train, len(draws)):
        train = draws[:index]
        for position in range(3):
            probabilities = distribution(train, position, alpha)
            actual = int(draws[index][position])
            for digit, probability in enumerate(probabilities):
                target = float(digit == actual)
                brier += (probability - target) ** 2
            p_actual = max(probabilities[actual], 1e-15)
            log_loss -= math.log(p_actual)
            predicted = max(range(10), key=lambda d: probabilities[d])
            calibration_n[predicted] += 1
            calibration[predicted] += float(predicted == actual)
            tested += 1
    calibration_error = sum(abs((calibration[d] / calibration_n[d]) - 0.1) for d in range(10) if calibration_n[d]) / 10
    return {"tested_positions": tested, "brier_score": brier / tested, "log_loss": log_loss / tested,
            "top1_rate": sum(calibration) / tested, "mean_top1_calibration_error": calibration_error,
            "alpha": alpha}


def empirical_p_value(bootstrap_means: list[float], observed: float) -> float:
    """One-tailed bootstrap p-value for H0: mean advantage <= 0.

    p = (1 + #{b: b >= observed}) / (B + 1). A small p indicates the observed
    advantage is unlikely under the bootstrap distribution of differences.
    """
    n = len(bootstrap_means)
    if n == 0:
        return float("nan")
    count = sum(1 for b in bootstrap_means if b >= observed)
    return (1 + count) / (n + 1)


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR correction.

    Returns adjusted p-values, monotone non-decreasing, capped at 1.0.
    """
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    adjusted = [0.0] * m
    prev = 0.0
    for rank, idx in enumerate(order, start=1):
        val = min(1.0, m * pvals[idx] / rank)
        prev = max(prev, val)
        adjusted[idx] = prev
    return adjusted


def main() -> int:
    p = argparse.ArgumentParser(description="福彩3D概率评分与校准")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--min-train", type=int, default=500)
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--out", type=Path, default=base / "reports" / "probability-latest.json")
    args = p.parse_args()
    draws = load(args.db)
    models = {}
    for spec in REGISTRY:
        if spec.distribution is None:
            continue
        models[spec.name] = score_with_distribution(spec.distribution, draws, args.min_train, args.alpha)
    # Backward-compatible aliases for any legacy consumer.
    models.setdefault("uniform", models.get("uniform_baseline", {}))
    models.setdefault("smoothed_position_frequency", models.get("position_frequency", {}))
    report = {
        "disclaimer": "概率评分是历史外推评估，不证明未来存在可利用优势。",
        "protocol": {"min_train": args.min_train, "tested_draws": len(draws) - args.min_train},
        "models": models,
        "interpretation": "Brier 和 Log Loss 越低越好；必须在同一时间窗口与均匀基线比较。",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Probability evaluation complete: {len(models)} models")
    print(f"Report: {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
