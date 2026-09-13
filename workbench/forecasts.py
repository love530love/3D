"""Multi-method forecast coexistence layer (workbench-internal analytics).

Design intent
-------------
The project already has `models_sd3d.REGISTRY`: several prediction methods that
share one `predict(train, top_k)` / `distribution(train, position, alpha)`
contract. This module is the *underlying layer that lets many methods coexist*:

  * For any target period it generates EVERY method's forecast using ONLY data
    strictly before that period (time-forward training, no leakage).
  * It stores each method's forecast side-by-side, keyed by (period, method),
    so they can be compared against the actual draw and against each other.
  * It computes deviation metrics (exact hit, position hits, digit divergence,
    log-loss where a distribution exists).

Crucially this does NOT touch the project's authoritative `sd3d_history.sqlite3`
(charter Article 2). The forecast board lives in a SEPARATE analytical cache so
the change stays L1 (additive tooling, no data-semantics change).
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

CACHE_DB = Path(__file__).resolve().parent / "forecasts_cache.sqlite3"

# Make the project root importable so we can reuse the REGISTRY.
ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import models_sd3d  # noqa: E402


def _connect() -> sqlite3.Connection:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(CACHE_DB))
    c.execute(
        """CREATE TABLE IF NOT EXISTS forecasts (
            period TEXT NOT NULL,
            method_id TEXT NOT NULL,
            candidates_json TEXT NOT NULL,
            distribution_json TEXT,
            params_json TEXT,
            training_cutoff TEXT,
            created_at TEXT,
            PRIMARY KEY (period, method_id)
        )"""
    )
    return c


def load_numbers(db: Path, upto_period: str | None = None) -> list[tuple[str, str]]:
    """Return (period, number) pairs, optionally excluding period >= upto_period."""
    out: list[tuple[str, str]] = []
    try:
        with sqlite3.connect(str(db)) as c:
            rows = c.execute(
                "SELECT period,values_json FROM draws ORDER BY CAST(period AS INTEGER)"
            ).fetchall()
    except Exception:
        return out
    for period, payload in rows:
        if upto_period is not None and int(period) >= int(upto_period):
            continue
        try:
            fields = json.loads(payload)
            number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        except Exception:
            continue
        if len(number) == 3:
            out.append((str(period), number))
    return out


def generate_for_period(db: Path, period: str, top_k: int = 10, alpha: float = 0.1) -> list[dict]:
    """Generate every REGISTRY method's forecast for `period` from prior data."""
    nums_all = load_numbers(db)
    train = [n for (p, n) in nums_all if int(p) < int(period)]
    cutoff = nums_all[-1][0] if nums_all else None
    forecasts: list[dict] = []
    for spec in models_sd3d.REGISTRY:
        candidates = spec.predict(train, top_k)
        distribution = None
        if spec.distribution is not None:
            try:
                distribution = [spec.distribution(train, i, alpha) for i in range(3)]
            except Exception:
                distribution = None
        forecasts.append(
            {
                "method_id": spec.name,
                "description": spec.description,
                "candidates": candidates,
                "distribution": distribution,
                "params": {"top_k": top_k, "alpha": alpha},
                "training_cutoff": cutoff,
            }
        )
    return forecasts


def store_forecasts(period: str, forecasts: list[dict]) -> None:
    c = _connect()
    try:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for f in forecasts:
            c.execute(
                "INSERT OR REPLACE INTO forecasts "
                "(period, method_id, candidates_json, distribution_json, params_json, training_cutoff, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    period,
                    f["method_id"],
                    json.dumps(f["candidates"], ensure_ascii=False),
                    json.dumps(f["distribution"], ensure_ascii=False) if f["distribution"] else None,
                    json.dumps(f["params"], ensure_ascii=False),
                    f.get("training_cutoff"),
                    now,
                ),
            )
        c.commit()
    finally:
        c.close()


def get_forecasts(period: str) -> list[dict]:
    c = _connect()
    try:
        rows = c.execute(
            "SELECT method_id, candidates_json, distribution_json, params_json, training_cutoff "
            "FROM forecasts WHERE period=?",
            (period,),
        ).fetchall()
    finally:
        c.close()
    out = []
    for method_id, cj, dj, pj, cutoff in rows:
        out.append(
            {
                "method_id": method_id,
                "candidates": json.loads(cj),
                "distribution": json.loads(dj) if dj else None,
                "params": json.loads(pj) if pj else {},
                "training_cutoff": cutoff,
            }
        )
    return out


def evaluate(actual: str, candidates: list[str], distribution: list[list[float]] | None) -> dict:
    pred = candidates[0] if candidates else ""
    exact = actual in candidates
    pos_top1 = sum(1 for i in range(3) if i < len(pred) and pred[i] == actual[i]) if pred else 0
    pos_topk = (
        sum(1 for i in range(3) if any(c[i] == actual[i] for c in candidates[: max(10, len(candidates))]))
        if candidates
        else 0
    )
    div = (
        sum(abs(int(actual[i]) - int(pred[i])) for i in range(3) if i < len(pred))
        if pred
        else None
    )
    ll = None
    if distribution:
        eps = 1e-9
        ll = -sum(math.log(max(distribution[i][int(actual[i])], eps)) for i in range(3)) / 3.0
    return {
        "exact_hit": exact,
        "position_top1_hits": pos_top1,
        "position_topk_hits": pos_topk,
        "digit_divergence": div,
        "log_loss": ll,
    }


def actual_for(db: Path, period: str) -> str | None:
    try:
        with sqlite3.connect(str(db)) as c:
            row = c.execute("SELECT values_json FROM draws WHERE period=?", (period,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    fields = json.loads(row[0])
    number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
    return number if len(number) == 3 else None


def draw_date(db: Path, period: str) -> str | None:
    """Return the draw date string for a period (last field of values_json), or None."""
    try:
        with sqlite3.connect(str(db)) as c:
            row = c.execute("SELECT values_json FROM draws WHERE period=?", (period,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    try:
        fields = json.loads(row[0])
        return fields[-1] if fields else None
    except Exception:
        return None


def compare_period(db: Path, period: str, top_k: int = 10, alpha: float = 0.1, use_cache: bool = True) -> dict:
    """Compare every method's forecast for `period` against the actual draw."""
    cached = get_forecasts(period) if use_cache else []
    if not cached:
        cached = generate_for_period(db, period, top_k, alpha)
        store_forecasts(period, cached)
    actual = actual_for(db, period)
    d = draw_date(db, period)
    methods = []
    for f in cached:
        metrics = evaluate(actual, f["candidates"], f["distribution"]) if actual else None
        methods.append(
            {
                "method_id": f["method_id"],
                "candidates": f["candidates"][:10],
                "metrics": metrics,
            }
        )
    return {"period": period, "actual": actual, "date": d, "methods": methods}


def compare_window(db: Path, last_n: int = 12, top_k: int = 10, alpha: float = 0.1) -> dict:
    """Rigorous multi-method backtest over the last `last_n` periods.

    For each of the last N periods we predict from strictly earlier data and
    score against the actual, then aggregate per method. Ends at the last actual.
    """
    nums = load_numbers(db)
    if len(nums) <= last_n:
        last_n = max(1, len(nums) - 1)
    targets = nums[-last_n:]
    agg: dict[str, dict] = {}
    periods_used = []
    for period, actual in targets:
        forecasts = generate_for_period(db, period, top_k, alpha)
        for f in forecasts:
            m = evaluate(actual, f["candidates"], f["distribution"])
            a = agg.setdefault(
                f["method_id"],
                {"exact": 0, "pos_top1": 0, "pos_topk": 0, "div_sum": 0.0, "ll_sum": 0.0, "n": 0},
            )
            a["exact"] += int(m["exact_hit"])
            a["pos_top1"] += m["position_top1_hits"]
            a["pos_topk"] += m["position_topk_hits"]
            if m["digit_divergence"] is not None:
                a["div_sum"] += m["digit_divergence"]
            if m["log_loss"] is not None:
                a["ll_sum"] += m["log_loss"]
            a["n"] += 1
        periods_used.append(period)
    per_method = {}
    for mid, a in agg.items():
        n = a["n"] or 1
        per_method[mid] = {
            "exact_rate": a["exact"] / n,
            "mean_position_top1": a["pos_top1"] / (3 * n),
            "mean_position_topk": a["pos_topk"] / (3 * n),
            "mean_digit_divergence": a["div_sum"] / n,
            "mean_log_loss": a["ll_sum"] / n if a["ll_sum"] else None,
            "n": n,
        }
    return {
        "window_size": last_n,
        "periods": periods_used,
        "per_method": per_method,
        "disclaimer": "多方法历史严格时间窗口对比（每期仅用更早数据）；不构成可预测性证明。",
    }


def next_period(db: Path, top_k: int = 10, alpha: float = 0.1) -> dict:
    """Forecast for the NEXT (not-yet-drawn) period from all strictly-earlier data.

    Leakage-free: trained only on periods before the latest known draw. There is
    no actual result yet, so this is a pure multi-method forecast for blind review.
    """
    nums = load_numbers(db)
    if not nums:
        return {"period": None, "trained_on_periods_up_to": None, "methods": []}
    last_period = nums[-1][0]
    next_p = str(int(last_period) + 1)
    forecasts = generate_for_period(db, next_p, top_k, alpha)
    return {
        "period": next_p,
        "trained_on_periods_up_to": last_period,
        "trained_on_date": draw_date(db, last_period),
        "methods": [
            {
                "method_id": f["method_id"],
                "candidates": (f["candidates"] or [])[:top_k],
                "distribution": f["distribution"],
            }
            for f in forecasts
        ],
    }


def historical_compare(db: Path, period: str, top_k: int = 10, alpha: float = 0.1, use_cache: bool = False) -> dict:
    """A past period's strictly-time-forward forecast vs its actual draw."""
    return compare_period(db, period, top_k, alpha, use_cache=use_cache)


def build_report(db: Path, last_n: int = 12, top_k: int = 10, alpha: float = 0.1, history_offset: int = 2) -> dict:
    from datetime import datetime, timezone

    nums = load_numbers(db)
    last_period = nums[-1][0] if nums else None
    last_actual = nums[-1][1] if nums else None
    hist_period = None
    if last_period and history_offset > 0:
        try:
            hist_period = str(int(last_period) - history_offset)
        except Exception:
            hist_period = None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {"last_n": last_n, "top_k": top_k, "alpha": alpha, "history_offset": history_offset},
        "last_period": last_period,
        "actual_last": last_actual,
        "last_period_compare": compare_period(db, last_period, top_k, alpha, use_cache=False) if last_period else None,
        "window_aggregate": compare_window(db, last_n, top_k, alpha),
        "next_period": next_period(db, top_k, alpha),
        "history_offset": history_offset,
        "historical_compare": historical_compare(db, hist_period, top_k, alpha) if hist_period else None,
    }
