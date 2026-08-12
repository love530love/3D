"""Freeze a transparent candidate forecast before the next draw is known."""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="冻结下一期福彩3D教学实验候选")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--out", type=Path, default=base / "predictions")
    p.add_argument("--top-k", type=int, default=10)
    args = p.parse_args()
    with sqlite3.connect(args.db) as c:
        rows = c.execute("SELECT period,values_json FROM draws ORDER BY CAST(period AS INTEGER)").fetchall()
    if not rows:
        raise SystemExit("数据库为空，无法冻结预测")
    numbers = []
    for _, payload in rows:
        fields = json.loads(payload)
        number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(number) == 3:
            numbers.append(number)
    cutoff = str(rows[-1][0])
    target = str(int(cutoff) + 1)
    counts = [Counter(number[i] for number in numbers) for i in range(3)]
    ranked = [sorted(counter, key=lambda digit: (-counter[digit], digit)) for counter in counts]
    candidates = [a + b + c for a in ranked[0][:3] for b in ranked[1][:3] for c in ranked[2][:3]][:args.top_k]
    run_id = uuid.uuid4().hex
    artifact = {
        "kind": "frozen_prediction",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training_cutoff_period": cutoff,
        "target_period": target,
        "training_draws": len(numbers),
        "model": "position_frequency_baseline_v1",
        "parameters": {"top_k": args.top_k, "candidate_grid_width": 3},
        "candidates": candidates,
        "position_rankings": ranked,
        "disclaimer": "这是冻结的统计教学实验，不构成预测能力或投注建议。",
    }
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"frozen-{target}-{run_id}.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Frozen prediction: {path.resolve()}")
    print(f"Training cutoff: {cutoff}; target: {target}")
    return 0


if __name__ == "__main__":
    main()
