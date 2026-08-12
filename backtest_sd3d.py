"""Leakage-resistant expanding-window backtest for transparent baselines."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path


def load(db: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(db) as c:
        raw = c.execute("SELECT period,values_json FROM draws ORDER BY CAST(period AS INTEGER)").fetchall()
    result = []
    for period, payload in raw:
        fields = json.loads(payload)
        number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(number) == 3:
            result.append((str(period), number))
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="严格时间顺序福彩3D基线回测")
    p.add_argument("--db", type=Path, default=Path(__file__).with_name("sd3d_history.sqlite3"))
    p.add_argument("--min-train", type=int, default=500)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--out", type=Path, default=Path(__file__).with_name("reports"))
    args = p.parse_args()
    try:
        draws = load(args.db)
        if len(draws) <= args.min_train:
            raise RuntimeError("样本不足以进行指定的时间回测")
        tested = 0
        exact_hits = 0
        position_hits = [0, 0, 0]
        predictions = []
        for index in range(args.min_train, len(draws)):
            train = [number for _, number in draws[:index]]
            actual_period, actual = draws[index]
            pos_counts = [Counter(number[i] for number in train) for i in range(3)]
            ranked_digits = [sorted(c, key=lambda d: (-c[d], d)) for c in pos_counts]
            candidates = [a + b + c for a in ranked_digits[0][:3] for b in ranked_digits[1][:3] for c in ranked_digits[2][:3]]
            candidates = candidates[:args.top_k]
            predictions.append({"period": actual_period, "frozen_before": actual_period, "candidates": candidates, "actual": actual})
            tested += 1
            exact_hits += actual in candidates
            position_hits = [n + int(actual[i] == ranked_digits[i][0]) for i, n in enumerate(position_hits)]
        report = {
            "disclaimer": "严格时间回测，不代表未来可预测；候选模型必须和随机基线比较。",
            "config": {"min_train": args.min_train, "top_k": args.top_k},
            "sample": {"total": len(draws), "tested": tested},
            "frequency_baseline": {
                "exact_top_k_hits": exact_hits,
                "exact_top_k_rate": exact_hits / tested,
                "position_top1_hits": position_hits,
                "position_top1_rates": [x / tested for x in position_hits],
            },
            "uniform_random_baseline": {
                "expected_exact_top_k_rate": args.top_k / 1000,
                "expected_position_top1_rate": 0.1,
            },
            "frozen_predictions": predictions,
        }
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / "backtest-latest.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Backtest complete: {tested} frozen predictions")
        print(f"Report: {path.resolve()}")
        return 0
    except Exception as exc:
        print(f"Backtest failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
