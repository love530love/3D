"""Paired bootstrap comparison of registered challenger exact-hit outcomes."""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from pathlib import Path

from models_sd3d import REGISTRY
from probability_metrics import empirical_p_value, benjamini_hochberg


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


def bootstrap_comparison(a: list[int], b: list[int], seed: int, repeats: int) -> dict:
    rng = random.Random(seed)
    differences = [x - y for x, y in zip(a, b)]
    n = len(differences)
    samples = [sum(differences[rng.randrange(n)] for _ in range(n)) / n for _ in range(repeats)]
    samples.sort()
    low = samples[int(0.025 * repeats)]
    high = samples[int(0.975 * repeats) - 1]
    observed = sum(differences) / n
    return {
        "observed_rate_difference": observed,
        "bootstrap_95ci": [low, high],
        "bootstrap_means": samples,
        "repeats": repeats,
        "interpretation": "区间跨过0时，不能据此认为模型有稳定优势。",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="模型配对 Bootstrap 差异比较（含 Benjamini–Hochberg FDR 校正）")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--min-train", type=int, default=500)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--repeats", type=int, default=1000)
    p.add_argument("--seed", type=int, default=20260812)
    p.add_argument("--out", type=Path, default=base / "reports" / "model-comparison-latest.json")
    args = p.parse_args()
    draws = load(args.db)
    base_model = REGISTRY[0]
    base_outcomes = outcomes(draws, args.min_train, args.top_k, base_model)
    comparisons = {}
    for spec in REGISTRY[1:]:
        challenger = outcomes(draws, args.min_train, args.top_k, spec)
        comparisons[spec.name] = bootstrap_comparison(challenger, base_outcomes, args.seed, args.repeats)
    # One-tailed empirical p-value and BH-FDR correction across the full battery.
    raw_p = {
        name: empirical_p_value(result["bootstrap_means"], result["observed_rate_difference"])
        for name, result in comparisons.items()
    }
    names = list(comparisons.keys())
    corrected = benjamini_hochberg([raw_p[name] for name in names])
    for i, name in enumerate(names):
        comparisons[name]["raw_p"] = raw_p[name]
        comparisons[name]["corrected_p"] = corrected[i]
        comparisons[name].pop("bootstrap_means", None)
    report = {
        "disclaimer": "Bootstrap 是不确定性估计，不是彩票可预测性的证明。多重比较已用 Benjamini–Hochberg FDR 校正。",
        "protocol": {
            "baseline": base_model.name,
            "min_train": args.min_train,
            "top_k": args.top_k,
            "tested": len(base_outcomes),
            "challengers": len(names),
            "fdr_method": "Benjamini-Hochberg",
            "p_value": "one-tailed bootstrap (1 + #{b >= observed}) / (B + 1)",
        },
        "comparisons_vs_uniform": comparisons,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Bootstrap comparisons complete: {len(comparisons)} challengers")
    print(f"Report: {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
