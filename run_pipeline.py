"""Run the read-only analysis pipeline in a deterministic, auditable order."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="运行福彩3D统计学习分析流水线")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--log", type=Path, default=base / "sd3d_history.jsonl")
    p.add_argument("--raw-dir", type=Path, default=base / "raw_snapshots")
    p.add_argument("--bootstrap-repeats", type=int, default=300)
    args = p.parse_args()
    common = ["--db", str(args.db)]
    steps = [
        ["validate_sd3d.py", "--db", str(args.db), "--log", str(args.log), "--raw-dir", str(args.raw_dir)],
        ["analyze_sd3d.py", *common],
        ["diagnose_sd3d.py", *common],
        ["evaluate_models.py", *common],
        ["probability_metrics.py", *common],
        ["compare_models_stats.py", *common, "--repeats", str(args.bootstrap_repeats)],
        ["build_teaching_report.py"],
        ["evidence_brain.py"],
    ]
    for step in steps:
        print(f"[pipeline] {' '.join(step)}")
        completed = subprocess.run([sys.executable, *step], cwd=base)
        if completed.returncode != 0:
            print(f"[pipeline] STOP: {step[0]} exit={completed.returncode}", file=sys.stderr)
            return completed.returncode
    print("[pipeline] PASS: all stages completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
