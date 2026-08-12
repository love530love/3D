"""Evidence-first 福彩3D analysis demo.

This module deliberately starts with transparent baselines. It does not claim
that frequency ranking predicts a random lottery; every output is labelled as
an experiment and can be compared with the uniform 1/1000 exact-combination
baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sqlite3
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_draws(db: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(db) as connection:
        rows = connection.execute("SELECT period, values_json FROM draws ORDER BY CAST(period AS INTEGER)").fetchall()
    result = []
    for period, payload in rows:
        fields = json.loads(payload)
        number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(number) == 3 and all(ch in "0123456789" for ch in number):
            result.append((str(period), number))
    if not result:
        raise RuntimeError("SQLite 中没有可分析的三位开奖号码")
    return result


def entropy(counter: Counter[str], total: int) -> float:
    return -sum((n / total) * math.log2(n / total) for n in counter.values() if n)


def analyze(draws: list[tuple[str, str]], seed: int) -> dict:
    numbers = [number for _, number in draws]
    digit_counts = Counter("".join(numbers))
    position_counts = [Counter(number[i] for number in numbers) for i in range(3)]
    sums = Counter(sum(int(ch) for ch in number) for number in numbers)
    exact_counts = Counter(numbers)
    repeats = Counter("repeat" if len(set(number)) < 3 else "all_distinct" for number in numbers)
    random.seed(seed)
    random_probe = [f"{random.randrange(1000):03d}" for _ in range(10000)]
    random_exact = Counter(random_probe)
    ranked = sorted(exact_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
    total = len(numbers)
    return {
        "disclaimer": "实验性统计输出，不构成预测、投注建议或稳定优势证明。",
        "sample": {"draw_count": total, "first_period": draws[0][0], "last_period": draws[-1][0]},
        "descriptive": {
            "digit_frequency": dict(sorted(digit_counts.items())),
            "position_frequency": [dict(sorted(counter.items())) for counter in position_counts],
            "sum_frequency": {str(k): v for k, v in sorted(sums.items())},
            "shape_frequency": dict(repeats),
            "digit_entropy_bits": entropy(digit_counts, total * 3),
            "exact_top20": [{"number": n, "count": c, "rate": c / total} for n, c in ranked],
        },
        "random_baseline": {
            "exact_combination_probability": 1 / 1000,
            "expected_exact_count_in_sample": total / 1000,
            "monte_carlo_draws": len(random_probe),
            "monte_carlo_top_frequency": max(random_exact.values()),
            "interpretation": "频率偏差需要时间外推和置换检验，不能直接视为可预测信号。",
        },
        "experimental_outputs": {
            "frequency_rank_candidates": [n for n, _ in ranked[:10]],
            "excluded_by_repeat_rule": "all_distinct only",
            "exclusion_warning": "排除规则可能误删真实结果，必须在冻结预测后的盲评中统计。",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成透明的福彩3D统计实验报告")
    parser.add_argument("--db", type=Path, default=Path(__file__).with_name("sd3d_history.sqlite3"))
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("reports"))
    parser.add_argument("--seed", type=int, default=20260812)
    args = parser.parse_args()
    try:
        draws = load_draws(args.db)
        report = analyze(draws, args.seed)
        run_id = uuid.uuid4().hex
        manifest = {
            "run_id": run_id, "created_at": now(), "db": str(args.db.resolve()),
            "db_sha256": hashlib.sha256(args.db.read_bytes()).hexdigest(),
            "seed": args.seed, "draw_count": len(draws), "analysis_version": "baseline-v1",
        }
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"analysis-{run_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.out / f"manifest-{run_id}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Analysis complete: {len(draws)} draws")
        print(f"Report directory: {args.out.resolve()}")
        return 0
    except Exception as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
