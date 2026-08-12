"""Replay an immutable HTML snapshot without contacting the source website."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fetch_sd3d import extract_draw_rows, extract_rows


def main() -> int:
    p = argparse.ArgumentParser(description="离线重放福彩3D原始 HTML 快照")
    p.add_argument("snapshot", type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    raw = args.snapshot.read_bytes()
    text = raw.decode("utf-8")
    rows = extract_draw_rows(extract_rows(text))
    result = {
        "snapshot": str(args.snapshot.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "draw_rows": len(rows),
        "first_period": rows[0][0] if rows else None,
        "last_period": rows[-1][0] if rows else None,
        "status": "PASS" if rows else "FAIL",
    }
    output = args.out or args.snapshot.with_suffix(".replay.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Replay: {result['status']}; draw rows: {result['draw_rows']}")
    print(f"Report: {output.resolve()}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
