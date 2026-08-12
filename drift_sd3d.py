"""Rolling distribution drift diagnostics for the evidence brain."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path


def js_divergence(a: Counter, b: Counter, keys: list[str]) -> float:
    total_a, total_b = sum(a.values()), sum(b.values())
    p = [(a[k] + 1) / (total_a + len(keys)) for k in keys]
    q = [(b[k] + 1) / (total_b + len(keys)) for k in keys]
    m = [(x + y) / 2 for x, y in zip(p, q)]
    return 0.5 * sum(x * math.log2(x / z) for x, z in zip(p, m)) + 0.5 * sum(y * math.log2(y / z) for y, z in zip(q, m))


def load(db: Path) -> list[str]:
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT values_json FROM draws ORDER BY CAST(period AS INTEGER)").fetchall()
    out = []
    for (payload,) in rows:
        fields = json.loads(payload)
        number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(number) == 3:
            out.append(number)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="检测福彩3D历史与近期分布漂移")
    base = Path(__file__).parent
    p.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    p.add_argument("--window", type=int, default=500)
    p.add_argument("--out", type=Path, default=base / "reports" / "drift-latest.json")
    args = p.parse_args()
    draws = load(args.db)
    recent = draws[-args.window:]
    prior = draws[:-args.window] or draws
    digit_keys = list("0123456789")
    all_digits = Counter("".join(prior))
    recent_digits = Counter("".join(recent))
    all_sums = Counter(str(sum(map(int, n))) for n in prior)
    recent_sums = Counter(str(sum(map(int, n))) for n in recent)
    all_shapes = Counter("repeat" if len(set(n)) < 3 else "all_distinct" for n in prior)
    recent_shapes = Counter("repeat" if len(set(n)) < 3 else "all_distinct" for n in recent)
    result = {
        "disclaimer": "漂移表示窗口分布变化，不代表存在可利用的预测原因。",
        "sample": {"total": len(draws), "recent_window": len(recent), "prior_window": len(prior)},
        "js_divergence": {
            "digits": js_divergence(all_digits, recent_digits, digit_keys),
            "sums": js_divergence(all_sums, recent_sums, [str(i) for i in range(28)]),
            "shapes": js_divergence(all_shapes, recent_shapes, ["repeat", "all_distinct"]),
        },
        "action": "REVIEW_ONLY",
        "action_reason": "漂移检测只触发窗口复核，不自动切换模型或修改历史规则。",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Drift diagnostics complete: recent window {len(recent)}")
    print(f"Report: {args.out.resolve()}")


if __name__ == "__main__":
    main()
