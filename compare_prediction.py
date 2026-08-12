"""Compare a frozen prediction with an actually stored future draw."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="冻结预测与实际开奖盲评对比")
    base = Path(__file__).parent
    p.add_argument("prediction", type=Path)
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    artifact = json.loads(args.prediction.read_text(encoding="utf-8"))
    target = str(artifact["target_period"])
    with sqlite3.connect(args.db) as c:
        row = c.execute("SELECT values_json FROM draws WHERE period=?", (target,)).fetchone()
    if row is None:
        print(f"Pending: actual period {target} is not in SQLite yet")
        return 2
    fields = json.loads(row[0])
    actual = "".join(ch for ch in str(fields[1]) if ch.isdigit())
    candidates = artifact["candidates"]
    result = {
        "kind": "frozen_prediction_comparison",
        "compared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prediction_file": str(args.prediction.resolve()),
        "target_period": target,
        "training_cutoff_period": artifact["training_cutoff_period"],
        "actual": actual,
        "candidates": candidates,
        "exact_hit": actual in candidates,
        "position_hits": [sum(1 for i in range(3) if actual[i] == candidate[i]) for candidate in candidates],
        "warning": "单期命中或未命中都不能证明或否定可预测性。",
    }
    output = args.out or args.prediction.with_name(args.prediction.stem + "-comparison.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Compared: {output.resolve()}")
    print(f"Actual: {actual}; exact hit: {result['exact_hit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
