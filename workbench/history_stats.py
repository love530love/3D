"""Human-facing historical & official-style statistics (read-only analytics).

This module is the *human visual management* layer the dashboard was missing:
it turns the authoritative `sd3d_history.sqlite3` into observable history — a raw
draw table, sum/span trends, and official-site-style multi-dimensional stats
(frequency, omission, parity/size, group-type, hot/cold) plus a rolling
prediction-vs-actual board reusing the leakage-free forecasts layer.

CHARTER COMPLIANCE (PROJECT_CHARTER.md):
  * Read-only over the authoritative DB. Never writes, mutates, or deletes data.
  * Strictly time-forward for any prediction (reuses workbench.forecasts).
  * Additive tooling only -> L1 (no data-semantics change, no expert audit need).
  * No claim of predictability; a disclaimer is attached to every report.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Make the project root importable so we can reuse REGISTRY + forecasts.
ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import models_sd3d  # noqa: E402
from . import forecasts as fm  # noqa: E402

PRIME_DIGITS = {2, 3, 5, 7}


def _group_type(digits: list[int]) -> str:
    if len(set(digits)) == 1:
        return "豹子"
    if len(set(digits)) == 2:
        return "组三"
    return "组六"


def load_all(db: Path) -> list[dict]:
    """Return every draw as a derived record, ascending by period. Read-only."""
    out: list[dict] = []
    try:
        with sqlite3.connect(str(db)) as c:
            rows = c.execute(
                "SELECT period,values_json FROM draws ORDER BY CAST(period AS INTEGER)"
            ).fetchall()
    except Exception:
        return out
    for period, payload in rows:
        try:
            fields = json.loads(payload)
            number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
            if len(number) != 3:
                continue
            date = fields[-1] if fields else None
            digits = [int(x) for x in number]
            parity = ["奇" if d % 2 else "偶" for d in digits]
            size = ["大" if d >= 5 else "小" for d in digits]
            rec = {
                "period": str(period),
                "date": date,
                "number": f"{digits[0]} {digits[1]} {digits[2]}",
                "digits": digits,
                "sum": sum(digits),
                "span": max(digits) - min(digits),
                "parity": parity,
                "parity_pattern": "".join(parity),
                "parity_ratio": f"{sum(1 for d in digits if d % 2)}奇{3 - sum(1 for d in digits if d % 2)}偶",
                "size": size,
                "size_pattern": "".join(size),
                "type": _group_type(digits),
            }
            out.append(rec)
        except Exception:
            continue
    return out


def sum_distribution(recs: list[dict]) -> dict:
    dist = {str(k): 0 for k in range(0, 28)}
    for r in recs:
        dist[str(r["sum"])] = dist.get(str(r["sum"]), 0) + 1
    return dist


def span_distribution(recs: list[dict]) -> dict:
    dist = {str(k): 0 for k in range(0, 10)}
    for r in recs:
        dist[str(r["span"])] = dist.get(str(r["span"]), 0) + 1
    return dist


def position_frequency(recs: list[dict]) -> dict:
    freq = {str(p): {str(d): 0 for d in range(10)} for p in range(3)}
    for r in recs:
        for p in range(3):
            freq[str(p)][str(r["digits"][p])] += 1
    return freq


def position_omission(all_recs: list[dict]) -> dict:
    """Current omission per (position, digit): periods since the digit last appeared
    up to the latest draw. Computed over the FULL history so it is meaningful."""
    last = {str(p): {str(d): -1 for d in range(10)} for p in range(3)}
    for idx, rec in enumerate(all_recs):
        for p in range(3):
            last[str(p)][str(rec["digits"][p])] = idx
    n = len(all_recs)
    return {str(p): {str(d): (n - 1 - last[str(p)][str(d)]) for d in range(10)} for p in range(3)}


def parity_size_stats(recs: list[dict]) -> dict:
    parity_ratio: dict[str, int] = {}
    size_pattern: dict[str, int] = {}
    zhihe_pattern: dict[str, int] = {}
    zhi_total = he_total = 0
    for rec in recs:
        parity_ratio[rec["parity_ratio"]] = parity_ratio.get(rec["parity_ratio"], 0) + 1
        size_pattern[rec["size_pattern"]] = size_pattern.get(rec["size_pattern"], 0) + 1
        zh = sum(1 for d in rec["digits"] if d in PRIME_DIGITS)
        zp = f"{zh}质{3 - zh}合"
        zhihe_pattern[zp] = zhihe_pattern.get(zp, 0) + 1
        zhi_total += zh
        he_total += 3 - zh
    return {
        "parity_ratio": parity_ratio,
        "size_pattern": size_pattern,
        "zhihe_pattern": zhihe_pattern,
        "zhi_total": zhi_total,
        "he_total": he_total,
    }


def type_stats(recs: list[dict]) -> dict:
    c = {"豹子": 0, "组三": 0, "组六": 0}
    for rec in recs:
        c[rec["type"]] = c.get(rec["type"], 0) + 1
    return c


def hot_cold(recs: list[dict], n: int) -> dict:
    window = recs[-n:] if n < len(recs) else recs
    counts = {str(d): 0 for d in range(10)}
    total = 0
    for rec in window:
        for d in rec["digits"]:
            counts[str(d)] += 1
            total += 1
    expected = round(total / 10.0, 1)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], int(kv[0])))
    return {
        "n": len(window),
        "expected": expected,
        "ranked": [
            {
                "digit": d,
                "count": c,
                "cls": "hot" if c > expected else ("cold" if c < expected else "neutral"),
            }
            for d, c in ranked
        ],
    }


def prediction_rolling(db: Path, pred_window: int = 20, top_k: int = 10, alpha: float = 0.1) -> dict:
    """Leakage-free rolling board: for the last `pred_window` periods, every
    REGISTRY method predicts from strictly earlier data, scored vs the actual."""
    allp = [r["period"] for r in load_all(db)]
    if not allp:
        return {"periods": [], "methods": []}
    targets = allp[-pred_window:]
    method_ids = [m.name for m in models_sd3d.REGISTRY]
    cells_by_method = {mid: [] for mid in method_ids}
    periods = []
    for period in targets:
        actual = fm.actual_for(db, period)
        date = fm.draw_date(db, period)
        periods.append({"period": period, "actual": actual, "date": date})
        forecasts = fm.generate_for_period(db, period, top_k, alpha)
        for f in forecasts:
            m = fm.evaluate(actual, f["candidates"], f["distribution"])
            cells_by_method[f["method_id"]].append(
                {
                    "top1": (f["candidates"] or ["-"])[0],
                    "exact_hit": m["exact_hit"],
                    "pos_hits": m["position_top1_hits"],
                }
            )
    return {
        "periods": periods,
        "methods": [{"method_id": mid, "cells": cells_by_method[mid]} for mid in method_ids],
    }


def build_report(db: Path, window: int = 60, pred_window: int = 20, top_k: int = 10, alpha: float = 0.1) -> dict:
    all_recs = load_all(db)
    if not all_recs:
        return {"error": "no data", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    recs = all_recs[-window:] if window < len(all_recs) else all_recs
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {"window": window, "pred_window": pred_window, "top_k": top_k, "alpha": alpha},
        "window": window,
        "count": len(recs),
        "records": recs,
        "sum_distribution": sum_distribution(recs),
        "span_distribution": span_distribution(recs),
        "position_frequency": position_frequency(recs),
        "position_omission": position_omission(all_recs),
        "parity_size": parity_size_stats(recs),
        "type_stats": type_stats(recs),
        "hot_cold": hot_cold(recs, min(window, len(recs))),
        "prediction_rolling": prediction_rolling(db, pred_window, top_k, alpha),
        "disclaimer": "历史统计仅供学习观察；彩票为随机过程，过去分布不预示未来，不构成任何投注建议。",
    }
