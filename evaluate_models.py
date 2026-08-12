"""Evaluate all registered challengers with one leakage-resistant protocol."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from models_sd3d import REGISTRY


def load(db: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT period,values_json FROM draws ORDER BY CAST(period AS INTEGER)").fetchall()
    result = []
    for period, payload in rows:
        fields = json.loads(payload)
        number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(number) == 3:
            result.append((str(period), number))
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="多 challenger 严格时间回测")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--min-train", type=int, default=500)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--out", type=Path, default=base / "reports" / "models-latest.json")
    args = p.parse_args()
    draws = load(args.db)
    if len(draws) <= args.min_train:
        raise SystemExit("样本不足")
    scores = {spec.name: {"description": spec.description, "tested": 0, "exact_hits": 0, "position_hits": [0, 0, 0]} for spec in REGISTRY}
    for index in range(args.min_train, len(draws)):
        train = [number for _, number in draws[:index]]
        actual = draws[index][1]
        for spec in REGISTRY:
            candidates = spec.predict(train, args.top_k)
            score = scores[spec.name]
            score["tested"] += 1
            score["exact_hits"] += int(actual in candidates)
            for position in range(3):
                score["position_hits"][position] += int(any(candidate[position] == actual[position] for candidate in candidates))
    for score in scores.values():
        n = score["tested"]
        score["exact_hit_rate"] = score["exact_hits"] / n
        score["position_hit_rates"] = [value / n for value in score["position_hits"]]
    report = {
        "disclaimer": "同一时间回测协议下的教学比较，不代表任何稳定预测能力。",
        "protocol": {"min_train": args.min_train, "top_k": args.top_k, "tested": len(draws) - args.min_train},
        "random_reference": {"expected_exact_top_k_rate": args.top_k / 1000, "expected_single_position_rate": 0.1},
        "models": scores,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Model evaluation complete: {len(REGISTRY)} models")
    print(f"Report: {args.out.resolve()}")


if __name__ == "__main__":
    main()
