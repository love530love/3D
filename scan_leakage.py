"""Scan frozen artifacts for common temporal and outcome leakage."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="扫描冻结预测中的时序/结果泄漏")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--predictions", type=Path, default=base / "predictions")
    p.add_argument("--out", type=Path, default=base / "reports" / "leakage-latest.json")
    args = p.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    scanned = 0
    with sqlite3.connect(args.db) as connection:
        periods = {str(row[0]) for row in connection.execute("SELECT period FROM draws")}
    for path in sorted(args.predictions.glob("frozen-*.json")):
        scanned += 1
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            cutoff = int(artifact["training_cutoff_period"])
            target = int(artifact["target_period"])
            if target <= cutoff:
                errors.append(f"{path.name}: target_period not after training cutoff")
            if "actual" in artifact:
                errors.append(f"{path.name}: frozen artifact contains actual outcome")
            candidates = artifact.get("candidates", [])
            if not candidates or any(len(str(candidate)) != 3 or not str(candidate).isdigit() for candidate in candidates):
                errors.append(f"{path.name}: invalid candidate format")
            if target in [int(period) for period in periods] and not path.with_name(path.stem + "-comparison.json").exists():
                warnings.append(f"{path.name}: actual target exists but comparison artifact is missing")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if artifact.get("prediction_sha256") and artifact["prediction_sha256"] != digest:
                errors.append(f"{path.name}: prediction hash mismatch")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{path.name}: unreadable artifact: {exc}")
    result = {"status": "PASS" if not errors else "FAIL", "scanned": scanned,
              "errors": errors, "warnings": warnings,
              "policy": "发现泄漏时停止发布，不删除或改写历史预测。"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Leakage scan: {result['status']}; scanned={scanned}")
    print(f"Report: {args.out.resolve()}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
