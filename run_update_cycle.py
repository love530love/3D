"""Safe daily cycle: compare old freezes, ingest, validate, analyze, freeze."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(base: Path, args: list[str]) -> int:
    return subprocess.run([sys.executable, *args], cwd=base).returncode


def main() -> int:
    p = argparse.ArgumentParser(description="运行福彩3D增量更新与盲评周期")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--log", type=Path, default=base / "sd3d_history.jsonl")
    p.add_argument("--raw-dir", type=Path, default=base / "raw_snapshots")
    p.add_argument("--no-fetch", action="store_true", help="仅用于离线演练，不访问网络")
    p.add_argument("--skip-pipeline", action="store_true")
    args = p.parse_args()
    predictions = sorted((base / "predictions").glob("frozen-*.json"))
    if not args.no_fetch:
        for prediction in predictions:
            result = run(base, ["compare_prediction.py", str(prediction), "--db", str(args.db)])
            if result not in (0, 2):
                return result
        result = run(base, ["fetch_sd3d.py", "--db", str(args.db), "--log", str(args.log)])
        if result != 0:
            return result
    result = run(base, ["validate_sd3d.py", "--db", str(args.db), "--log", str(args.log), "--raw-dir", str(args.raw_dir)])
    if result != 0:
        return result
    if not args.skip_pipeline:
        result = run(base, ["run_pipeline.py", "--db", str(args.db), "--log", str(args.log), "--raw-dir", str(args.raw_dir), "--bootstrap-repeats", "100"])
        if result != 0:
            return result
    # Do not create duplicate freezes while an earlier target is still pending.
    pending = False
    for prediction in predictions:
        try:
            artifact = json.loads(prediction.read_text(encoding="utf-8"))
            with __import__("sqlite3").connect(args.db) as connection:
                exists = connection.execute("SELECT 1 FROM draws WHERE period=?", (str(artifact["target_period"]),)).fetchone()
            pending = pending or exists is None
        except (OSError, ValueError, KeyError):
            continue
    if not pending:
        result = run(base, ["predict_sd3d.py", "--db", str(args.db)])
        if result != 0:
            return result
    print("Update cycle PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
