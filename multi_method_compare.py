#!/usr/bin/env python3
"""Multi-method comparison report generator (workbench glue script).

Generates, for the latest period and a trailing window, every method's forecast
from models_sd3d.REGISTRY, scores each against the actual draw (leakage-free,
strictly time-forward), and writes reports/multi-method-latest.json for the
decision dashboard.

Pure standard library. Does NOT mutate the authoritative sd3d_history.sqlite3;
forecasts are cached in workbench/forecasts_cache.sqlite3 (charter Article 2).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import workbench.forecasts as fm  # noqa: E402

DB = ROOT / "sd3d_history.sqlite3"
OUT = ROOT / "reports" / "multi-method-latest.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="多方法预测对比报告（底层多种预测方式共存）")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--last-n", type=int, default=12, help="回看期数（严格时间顺序窗口）")
    ap.add_argument("--top-k", type=int, default=10, help="每方法候选数")
    ap.add_argument("--alpha", type=float, default=0.1, help="分布平滑系数")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)

    report = fm.build_report(a.db, last_n=a.last_n, top_k=a.top_k, alpha=a.alpha)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {a.out}")
    print(f"配置: {report['config']}")
    lp = report.get("last_period_compare") or {}
    print(f"最近一期 期号={report.get('last_period')} 实开={report.get('actual_last')}")
    for m in lp.get("methods", []):
        met = m.get("metrics") or {}
        top1 = (m.get("candidates") or ["-"])[0]
        print(f"  {m['method_id']:<28} top1={top1} 精确={met.get('exact_hit')} "
              f"位命中={met.get('position_top1_hits')} 偏差={met.get('digit_divergence')}")
    wa = report.get("window_aggregate") or {}
    print(f"近 {wa.get('window_size')} 期聚合:")
    for mid, s in (wa.get("per_method") or {}).items():
        ll = f"{s['mean_log_loss']:.3f}" if s.get("mean_log_loss") is not None else "-"
        print(f"  {mid:<28} 精确率={s['exact_rate']*100:5.1f}% "
              f"均位命中={s['mean_position_top1']*100:5.1f}% 均偏差={s['mean_digit_divergence']:.2f} ll={ll}")
    print(f"备注: {wa.get('disclaimer','')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
