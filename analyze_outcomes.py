"""Aggregate completed frozen-prediction outcomes without changing them."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="分析冻结预测长期盲评结果")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--out", type=Path, default=base / "reports" / "outcomes-analysis-latest.json")
    args = p.parse_args()
    with sqlite3.connect(args.db) as connection:
        rows = connection.execute("""
            SELECT model, exact_hit, max_position_hits, candidate_count
            FROM prediction_outcomes WHERE status='completed'
        """).fetchall()
    grouped = defaultdict(list)
    for model, exact, max_hits, candidate_count in rows:
        grouped[model].append({"exact_hit": exact, "max_position_hits": max_hits, "candidate_count": candidate_count})
    models = {}
    for model, values in grouped.items():
        n = len(values)
        models[model] = {
            "completed": n,
            "exact_hits": sum(item["exact_hit"] or 0 for item in values),
            "exact_hit_rate": sum(item["exact_hit"] or 0 for item in values) / n,
            "mean_max_position_hits": sum(item["max_position_hits"] or 0 for item in values) / n,
            "candidate_count": values[-1]["candidate_count"],
        }
    result = {
        "completed_total": len(rows),
        "models": models,
        "status": "INSUFFICIENT盲评样本" if len(rows) < 30 else "DESCRIPTIVE_ONLY",
        "disclaimer": "盲评汇总是描述性证据；样本不足或单期命中不能证明预测优势。",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Outcome analysis: {len(rows)} completed records")
    print(f"Report: {args.out.resolve()}")


if __name__ == "__main__":
    main()
