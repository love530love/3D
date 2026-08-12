"""Data and audit-chain quality gate for the local 福彩3D store."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def validate_db(path: Path, raw_dir: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    with sqlite3.connect(path) as c:
        rows = c.execute("SELECT period,values_json,source_sha256 FROM draws ORDER BY CAST(period AS INTEGER)").fetchall()
        run_count = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    periods = [str(row[0]) for row in rows]
    if periods != sorted(set(periods), key=int):
        errors.append("期号不是唯一且严格可排序")
    snapshot_missing = 0
    snapshot_mismatch = 0
    latest_source_hash = None
    with sqlite3.connect(path) as c:
        latest_source_hash = c.execute("SELECT source_sha256 FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
    latest_source_hash = latest_source_hash[0] if latest_source_hash else None
    for period, payload, source_hash in rows:
        try:
            fields = json.loads(payload)
            number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
            if len(number) != 3 or any(ch not in "0123456789" for ch in number):
                errors.append(f"{period}: 开奖号码不是三位数字")
        except (ValueError, IndexError, TypeError) as exc:
            errors.append(f"{period}: JSON/字段损坏: {exc}")
        snapshot = raw_dir / f"{source_hash}.html"
        if not snapshot.exists():
            snapshot_missing += 1
        else:
            actual_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            if actual_hash != source_hash:
                snapshot_mismatch += 1
    if snapshot_missing:
        if latest_source_hash and not (raw_dir / f"{latest_source_hash}.html").exists():
            errors.append("最新运行来源快照缺失")
        else:
            warnings.append(f"历史数据缺少原始快照: {snapshot_missing} 条（快照功能启用前产生）")
    if snapshot_mismatch:
        errors.append(f"原始快照哈希不匹配: {snapshot_mismatch} 条")
    if not rows:
        errors.append("draws 表为空")
    if run_count == 0:
        warnings.append("尚无运行记录")
    return {"row_count": len(rows), "first_period": periods[0] if periods else None,
            "last_period": periods[-1] if periods else None, "run_count": run_count,
            "snapshot_missing": snapshot_missing, "snapshot_mismatch": snapshot_mismatch,
            "errors": errors, "warnings": warnings}


def validate_log(path: Path) -> dict:
    errors: list[str] = []
    previous = "GENESIS"
    count = 0
    if not path.exists():
        return {"event_count": 0, "errors": [f"日志不存在: {path}"], "warnings": []}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
            actual = event.pop("event_hash")
            if event.get("previous_hash") != previous:
                errors.append(f"第 {line_no} 行 previous_hash 不连续")
            expected = hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            if actual != expected:
                errors.append(f"第 {line_no} 行 event_hash 不匹配")
            previous = actual
            count += 1
        except (ValueError, KeyError) as exc:
            errors.append(f"第 {line_no} 行无法解析: {exc}")
    return {"event_count": count, "tail_hash": previous, "errors": errors, "warnings": []}


def main() -> int:
    p = argparse.ArgumentParser(description="验证福彩3D数据库和 JSONL 审计链")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--log", type=Path, default=base / "sd3d_history.jsonl")
    p.add_argument("--raw-dir", type=Path, default=base / "raw_snapshots")
    p.add_argument("--out", type=Path, default=base / "reports" / "quality-latest.json")
    args = p.parse_args()
    result = {"database": validate_db(args.db, args.raw_dir), "audit_log": validate_log(args.log)}
    result["status"] = "PASS" if not result["database"]["errors"] and not result["audit_log"]["errors"] else "FAIL"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Quality gate: {result['status']}")
    print(f"Report: {args.out.resolve()}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
