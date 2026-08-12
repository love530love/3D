"""Transparent randomness diagnostics using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from collections import Counter
from pathlib import Path


def load(path: Path) -> list[str]:
    with sqlite3.connect(path) as c:
        raw = c.execute("SELECT values_json FROM draws ORDER BY CAST(period AS INTEGER)").fetchall()
    numbers = []
    for (payload,) in raw:
        fields = json.loads(payload)
        number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(number) == 3:
            numbers.append(number)
    return numbers


def chi_square_uniform(values: list[str]) -> dict:
    counts = Counter(values)
    expected = len(values) / 10
    statistic = sum((counts[str(d)] - expected) ** 2 / expected for d in range(10))
    # Wilson-Hilferty approximation for chi-square(df=9) upper-tail p.
    z = ((statistic / 9) ** (1 / 3) - (1 - 2 / (9 * 9))) / math.sqrt(2 / (9 * 9))
    p_approx = 0.5 * math.erfc(z / math.sqrt(2))
    return {"statistic": statistic, "df": 9, "p_value_approx": p_approx,
            "counts": dict(sorted(counts.items())), "warning": "近似 p 值仅用于教学，需校正多重比较。"}


def runs(values: list[str]) -> dict:
    binary = [int(int(v) % 2 == 0) for v in values]
    ones = sum(binary)
    zeros = len(binary) - ones
    run_count = 1 + sum(binary[i] != binary[i - 1] for i in range(1, len(binary)))
    expected = 1 + 2 * ones * zeros / len(binary) if binary else 0
    variance = (2 * ones * zeros * (2 * ones * zeros - len(binary))) / (len(binary) ** 2 * (len(binary) - 1)) if len(binary) > 1 else 0
    z = (run_count - expected) / math.sqrt(variance) if variance > 0 else 0
    return {"runs": run_count, "expected_runs": expected, "z_score": z,
            "even_count": ones, "odd_count": zeros}


def lag_correlation(values: list[int], lag: int = 1) -> float:
    if len(values) <= lag:
        return 0.0
    a, b = values[:-lag], values[lag:]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    numerator = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    denominator = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return numerator / denominator if denominator else 0.0


def permutation_max_frequency(values: list[str], seed: int, repeats: int) -> dict:
    rng = random.Random(seed)
    observed = max(Counter(values).values())
    exceed = 0
    sample = list(values)
    for _ in range(repeats):
        rng.shuffle(sample)
        if max(Counter(sample).values()) >= observed:
            exceed += 1
    return {"observed_max_frequency": observed, "permutations": repeats,
            "p_value": (exceed + 1) / (repeats + 1),
            "interpretation": "检验频率峰值是否可由重排后的同一批数据产生。"}


def main() -> int:
    p = argparse.ArgumentParser(description="福彩3D随机性多角度诊断")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--out", type=Path, default=base / "reports" / "randomness-latest.json")
    p.add_argument("--seed", type=int, default=20260812)
    p.add_argument("--permutations", type=int, default=500)
    args = p.parse_args()
    numbers = load(args.db)
    digits = list("".join(numbers))
    result = {
        "disclaimer": "诊断结果不能证明下一期可预测；p 值不等于预测概率。",
        "sample_size_draws": len(numbers),
        "digit_uniformity": chi_square_uniform(digits),
        "parity_runs": runs([int(n[0]) for n in numbers]),
        "lag1_sum_correlation": lag_correlation([sum(map(int, n)) for n in numbers]),
        "lag1_digit_correlation": lag_correlation([int(n[0]) for n in numbers]),
        "permutation_peak_test": permutation_max_frequency(numbers, args.seed, args.permutations),
        "multiple_comparison_warning": "本报告包含多个探索性检验，不能挑选单个有利结果作为结论。",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Randomness diagnostics complete: {len(numbers)} draws")
    print(f"Report: {args.out.resolve()}")


if __name__ == "__main__":
    main()
