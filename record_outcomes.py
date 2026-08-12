"""Persist frozen-prediction outcomes once the target draw is available."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="记录冻结预测与实际结果的长期盲评")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--predictions", type=Path, default=base / "predictions")
    p.add_argument("--out", type=Path, default=base / "reports" / "outcomes-latest.json")
    args = p.parse_args()
    with sqlite3.connect(args.db) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                prediction_id TEXT PRIMARY KEY, target_period TEXT NOT NULL,
                training_cutoff_period TEXT NOT NULL, model TEXT NOT NULL,
                prediction_sha256 TEXT NOT NULL, actual TEXT, exact_hit INTEGER,
                max_position_hits INTEGER, candidate_count INTEGER NOT NULL,
                status TEXT NOT NULL, recorded_at TEXT NOT NULL
            )
        """)
        predictions = sorted(args.predictions.glob("frozen-*.json"))
        pending = completed = 0
        for path in predictions:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            prediction_id = artifact["run_id"]
            target = str(artifact["target_period"])
            row = connection.execute("SELECT values_json FROM draws WHERE period=?", (target,)).fetchone()
            actual = None
            exact = None
            max_hits = None
            status = "pending"
            if row is not None:
                fields = json.loads(row[0])
                actual = "".join(ch for ch in str(fields[1]) if ch.isdigit())
                candidates = artifact.get("candidates", [])
                exact = int(actual in candidates)
                max_hits = max((sum(a == b for a, b in zip(actual, candidate)) for candidate in candidates), default=0)
                status = "completed"
                completed += 1
            else:
                pending += 1
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            connection.execute("""
                INSERT INTO prediction_outcomes VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(prediction_id) DO UPDATE SET
                  actual=excluded.actual, exact_hit=excluded.exact_hit,
                  max_position_hits=excluded.max_position_hits, status=excluded.status,
                  recorded_at=excluded.recorded_at
            """, (prediction_id, target, str(artifact["training_cutoff_period"]), artifact.get("model", "unknown"),
                  digest, actual, exact, max_hits, len(artifact.get("candidates", [])), status,
                  datetime.now(timezone.utc).isoformat(timespec="seconds")))
        connection.commit()
        total = connection.execute("SELECT COUNT(*) FROM prediction_outcomes").fetchone()[0]
    result = {"total_predictions": total, "completed": completed, "pending": pending,
              "disclaimer": "盲评记录用于长期统计，不代表单期结果具有预测性。"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Outcome archive: {completed} completed; {pending} pending; {total} total")
    print(f"Report: {args.out.resolve()}")


if __name__ == "__main__":
    main()
