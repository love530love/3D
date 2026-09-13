#!/usr/bin/env python3
"""Historical & official-style statistics report generator (workbench glue script).

Builds the human-facing history view — raw draw table, sum/span trends, and
official-site-style multi-dimensional stats (frequency, omission, parity/size,
group-type, hot/cold), plus a leakage-free rolling prediction-vs-actual board —
and writes reports/history-stats-latest.json for the decision dashboard.

Pure standard library. Read-only over the authoritative sd3d_history.sqlite3;
does NOT mutate it (charter Article 2).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from workbench import history_stats as hs  # noqa: E402

DB = ROOT / "sd3d_history.sqlite3"
OUT = ROOT / "reports" / "history-stats-latest.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="历史与统计报告（人类视觉管理）")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--window", type=int, default=60, help="回看期数（历史开奖表与走势）")
    ap.add_argument("--pred-window", type=int, default=20, help="历史预测滚动对照期数")
    ap.add_argument("--top-k", type=int, default=10, help="每方法候选数")
    ap.add_argument("--alpha", type=float, default=0.1, help="分布平滑系数")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)

    report = hs.build_report(a.db, window=a.window, pred_window=a.pred_window, top_k=a.top_k, alpha=a.alpha)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {a.out}")
    print(f"配置: {report['config']} · 回看 {report['count']} 期")
    print(f"组选类型: {report['type_stats']}")
    hc = report["hot_cold"]
    print(f"冷热(近{hc['n']}期, 期望{hc['expected']}): " +
          " ".join(f"{r['digit']}:{r['count']}{'▲' if r['cls'] == 'hot' else ('▼' if r['cls'] == 'cold' else '')}" for r in hc["ranked"]))
    pr = report["prediction_rolling"]
    print(f"历史预测滚动对照: {len(pr['periods'])} 期 × {len(pr['methods'])} 方法")
    print(f"备注: {report['disclaimer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
