"""Probability scoring and calibration for position-wise lottery models."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path


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


def smoothed_distribution(train: list[str], position: int, alpha: float) -> list[float]:
    counts = Counter(number[position] for number in train)
    denominator = len(train) + 10 * alpha
    return [(counts[str(digit)] + alpha) / denominator for digit in range(10)]


def score(model: str, draws: list[str], min_train: int, alpha: float) -> dict:
    brier = 0.0
    log_loss = 0.0
    calibration = [0.0] * 10
    calibration_n = [0] * 10
    tested = 0
    for index in range(min_train, len(draws)):
        train = draws[:index]
        for position in range(3):
            if model == "uniform":
                probabilities = [0.1] * 10
            else:
                probabilities = smoothed_distribution(train, position, alpha)
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


def main() -> int:
    p = argparse.ArgumentParser(description="福彩3D概率评分与校准")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--min-train", type=int, default=500)
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--out", type=Path, default=base / "reports" / "probability-latest.json")
    args = p.parse_args()
    draws = load(args.db)
    report = {
        "disclaimer": "概率评分是历史外推评估，不证明未来存在可利用优势。",
        "protocol": {"min_train": args.min_train, "tested_draws": len(draws) - args.min_train},
        "models": {
            "uniform": score("uniform", draws, args.min_train, args.alpha),
            "smoothed_position_frequency": score("frequency", draws, args.min_train, args.alpha),
        },
        "interpretation": "Brier 和 Log Loss 越低越好；必须在同一时间窗口与均匀基线比较。",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Probability evaluation complete: {len(draws)} draws")
    print(f"Report: {args.out.resolve()}")


if __name__ == "__main__":
    main()
