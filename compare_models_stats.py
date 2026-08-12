"""Paired bootstrap comparison of registered challenger exact-hit outcomes."""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from pathlib import Path

from models_sd3d import REGISTRY


def load(db: Path) -> list[str]:
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT values_json FROM draws ORDER BY CAST(period AS INTEGER)").fetchall()
    out = []
    for (payload,) in rows:
        fields = json.loads(payload)
        number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(number) == 3:
            out.append(number)
    return out


def outcomes(draws: list[str], min_train: int, top_k: int, spec) -> list[int]:
    values = []
    for index in range(min_train, len(draws)):
        candidates = spec.predict(draws[:index], top_k)
        values.append(int(draws[index] in candidates))
    return values


def bootstrap_difference(a: list[int], b: list[int], seed: int, repeats: int) -> dict:
    rng = random.Random(seed)
    differences = [x - y for x, y in zip(a, b)]
    n = len(differences)
    samples = []
    for _ in range(repeats):
        samples.append(sum(differences[rng.randrange(n)] for _ in range(n)) / n)
    samples.sort()
    low = samples[int(0.025 * repeats)]
    high = samples[int(0.975 * repeats) - 1]
    return {"observed_rate_difference": sum(differences) / n, "bootstrap_95ci": [low, high],
            "repeats": repeats, "interpretation": "区间跨过0时，不能据此认为模型有稳定优势。"}


def main() -> int:
    p = argparse.ArgumentParser(description="模型配对 Bootstrap 差异比较")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--min-train", type=int, default=500)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--repeats", type=int, default=1000)
    p.add_argument("--out", type=Path, default=base / "reports" / "model-comparison-latest.json")
    args = p.parse_args()
    draws = load(args.db)
    base_model = REGISTRY[0]
    base_outcomes = outcomes(draws, args.min_train, args.top_k, base_model)
    comparisons = {}
    for spec in REGISTRY[1:]:
        challenger = outcomes(draws, args.min_train, args.top_k, spec)
        comparisons[spec.name] = bootstrap_difference(challenger, base_outcomes, 20260812, args.repeats)
    report = {"disclaimer": "Bootstrap 是不确定性估计，不是彩票可预测性的证明。",
              "protocol": {"baseline": base_model.name, "min_train": args.min_train, "top_k": args.top_k, "tested": len(base_outcomes)},
              "comparisons_vs_uniform": comparisons}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Bootstrap comparisons complete: {len(comparisons)} challengers")
    print(f"Report: {args.out.resolve()}")


if __name__ == "__main__":
    main()
