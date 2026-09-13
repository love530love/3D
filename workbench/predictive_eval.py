"""Honest backtest arena (模型竞技场) — strict time-forward evaluator.

Charter-compliant by construction:
  * Article 1  — treats the draw as a random process; the arena is a *hypothesis
                 test*, never a claim of predictability.
  * Article 2  — read-only over the authoritative DB (never mutates data).
  * Article 10 — every candidate scheme is compared against the *uniform random
                 baseline* with an exact binomial significance test; a scheme only
                 "wins" if it beats the baseline with statistical significance.

Core responsibilities
---------------------
1. Evaluate ANY predictor conforming to the REGISTRY ``predict(train, top_k)``
   contract over a strict expanding window (no leakage: each target is predicted
   from only earlier draws).
2. Compute exact-hit / position-hit / log-loss metrics and compare them against
   the uniform random baseline expectation, with hand-computed exact binomial
   p-values (pure standard library, no scipy).
3. Aggregate many schemes into a single "arena" report with an honesty layer and
   a genuine bias-correction improvement sweep (assume-then-test, not assume-and-
   pretend).

The expected result, as the user requested to "assume predictable and then fix via
backtest", is measured honestly — we run the attempt and *report what the data
says*, which for a near-uniform process will almost certainly be "no scheme beats
the baseline". That is the honest, charter-compliant outcome.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

# Theoretical log-loss of a perfectly calibrated uniform predictor:
#   E[-log p(d)] = -sum_{d=0..9} 0.1*log(0.1) = 2.302585...
THEORETICAL_LOG_LOSS = -math.log(0.1)


# ---------------------------------------------------------------------------
# Binomial helpers (no scipy; stable via lgamma / log1p)
# ---------------------------------------------------------------------------
def binom_pmf(k: int, n: int, p: float) -> float:
    if k < 0 or k > n:
        return 0.0
    if p <= 0.0:
        return 1.0 if k == 0 else 0.0
    if p >= 1.0:
        return 1.0 if k == n else 0.0
    logc = math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    return math.exp(logc + k * math.log(p) + (n - k) * math.log1p(-p))


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) under Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    # sum the right tail directly (cheap for our n up to ~1000)
    total = 0.0
    for i in range(k, n + 1):
        total += binom_pmf(i, n, p)
    return total


def binom_two_sided(observed: int, n: int, p0: float) -> float:
    """Exact two-sided binomial p-value (method of small probabilities)."""
    if n <= 0:
        return 1.0
    obs_pmf = binom_pmf(observed, n, p0)
    total = 0.0
    for k in range(n + 1):
        pk = binom_pmf(k, n, p0)
        if pk <= obs_pmf + 1e-15:
            total += pk
    return min(1.0, total)


def benjamini_hochberg(pvals: list[float], q: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg FDR correction. Returns per-test rejection flags.

    Critical for the arena: when many schemes are tested, raw α=0.05 significance
    is expected to produce false positives by chance. BH tells us which (if any)
    'beats-baseline' claims survive multiple-comparison control.
    """
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    rej = [False] * m
    largest_k = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= (rank / m) * q:
            largest_k = rank
    for rank, i in enumerate(order, start=1):
        if rank <= largest_k:
            rej[i] = True
    return rej


# ---------------------------------------------------------------------------
# Data loading (independent, read-only copy)
# ---------------------------------------------------------------------------
def load_numbers(db: Path) -> list[tuple[int, str]]:
    """Return [(period_int, number_str), ...] ordered by period, strictly digits."""
    out: list[tuple[int, str]] = []
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
        except Exception:
            continue
        if len(number) == 3:
            out.append((int(period), number))
    return out


# ---------------------------------------------------------------------------
# Predictor contract
# ---------------------------------------------------------------------------
@dataclass
class PredictorSpec:
    name: str
    description: str
    family: str
    predict: object  # (train: list[str], top_k: int) -> list[str]
    distribution: object = None  # (train, position, alpha) -> list[float] len 10


# ---------------------------------------------------------------------------
# Core evaluator
# ---------------------------------------------------------------------------
def evaluate_predictor(
    name: str,
    predict_fn,
    db: Path,
    last_n: int = 300,
    top_k: int = 10,
    alpha: float = 0.1,
    distribution_fn=None,
) -> dict:
    """Strict expanding-window backtest of a single predictor.

    For each of the last ``last_n`` actual draws we train on strictly earlier
    draws only, generate ``top_k`` candidates, then score against the actual.
    Returns aggregated metrics plus baseline comparison.
    """
    nums = load_numbers(db)
    if len(nums) <= 1:
        return {"error": "insufficient data"}
    if len(nums) <= last_n:
        last_n = max(1, len(nums) - 1)
    start = max(0, len(nums) - last_n)

    exact = 0
    pos_top1 = [0, 0, 0]
    pos_topk = 0
    div_sum = 0.0
    ll_sum = 0.0
    n = 0

    for i in range(start, len(nums)):
        period, actual = nums[i]
        train = [num for (_, num) in nums[:i]]
        if len(train) < 2:
            continue
        cands = predict_fn(train, top_k) or []
        n += 1

        # exact hit (top_k set)
        if actual in cands:
            exact += 1
        # position top-1 (first candidate)
        top1 = cands[0] if cands else ""
        if top1:
            for pos in range(3):
                if pos < len(top1) and top1[pos] == actual[pos]:
                    pos_top1[pos] += 1
        # position top-k (any of the k candidates)
        if cands:
            for pos in range(3):
                if any(c[pos] == actual[pos] for c in cands[: max(10, len(cands))]):
                    pos_topk += 1
        # digit divergence (first candidate)
        if top1:
            div = sum(abs(int(actual[pos]) - int(top1[pos])) for pos in range(3))
            div_sum += div
        # log-loss (if a distribution is supplied)
        if distribution_fn is not None:
            try:
                dist = [distribution_fn(train, pos, alpha) for pos in range(3)]
                eps = 1e-9
                ll = -sum(math.log(max(dist[pos][int(actual[pos])], eps)) for pos in range(3)) / 3.0
                ll_sum += ll
            except Exception:
                pass

    if n == 0:
        return {"error": "no evaluable targets"}

    exact_rate = exact / n
    p0_exact = top_k / 1000.0
    expected_exact = n * p0_exact
    two_sided_p = binom_two_sided(exact, n, p0_exact)
    exceeds_p = binom_sf(exact, n, p0_exact)  # P(X >= observed) under H0
    # left-tail p (worse than baseline)
    worse_p = 1.0 - binom_sf(exact - 1, n, p0_exact) if exact > 0 else 1.0

    mean_ll = ll_sum / n if ll_sum else None
    ll_delta = (mean_ll - THEORETICAL_LOG_LOSS) if mean_ll is not None else None

    pos_top1_rates = [pos_top1[p] / n for p in range(3)]
    pos_top1_p = [binom_two_sided(pos_top1[p], n, 0.10) for p in range(3)]

    # verdict
    if exact > expected_exact and exceeds_p < 0.05:
        verdict = "显著优于随机基线"
    elif exact < expected_exact and worse_p < 0.05:
        verdict = "显著劣于随机基线"
    else:
        verdict = "与随机基线无显著差异"

    if ll_delta is not None:
        if ll_delta < -0.05:
            calibration = "log-loss 低于理论值，疑似包含可预测信息"
        elif ll_delta > 0.05:
            calibration = "log-loss 高于理论值，过拟合/校准不良"
        else:
            calibration = "log-loss 接近理论值，未提供超出随机的信息"
    else:
        calibration = "无分布，无法计算 log-loss"

    return {
        "name": name,
        "n": n,
        "exact_hits": exact,
        "exact_rate": exact_rate,
        "expected_exact_rate": p0_exact,
        "expected_exact_hits": expected_exact,
        "two_sided_p": two_sided_p,
        "exceeds_baseline_p": exceeds_p,
        "worse_than_baseline_p": worse_p,
        "verdict": verdict,
        "mean_position_top1": pos_top1_rates,
        "position_top1_p": pos_top1_p,
        "position_topk_rate": pos_topk / (3 * n) if n else None,
        "mean_digit_divergence": div_sum / n,
        "mean_log_loss": mean_ll,
        "log_loss_delta_vs_theory": ll_delta,
        "calibration": calibration,
    }


# ---------------------------------------------------------------------------
# Improvement sweep — assume predictable, then test the fix (user direction #4)
# ---------------------------------------------------------------------------
def improvement_sweep(
    db: Path,
    builder,
    last_n: int = 200,
    top_k: int = 10,
    alpha: float = 0.1,
    windows=(50, 100, 200, 400),
    blends=(0.3, 0.5, 0.7),
) -> dict:
    """Genuinely *attempt* to improve a bias-correction predictor via backtest.

    builder(window, blend) -> (predict_fn, distribution_fn). We backtest every
    (window, blend) combination, keep the best by exact_rate, and honestly report
    whether even the best beats the uniform random baseline. This is the
    "assume predictable, then fix via backtest" loop made measurable.
    """
    trials = []
    best = None
    for window in windows:
        for blend in blends:
            predict_fn, dist_fn = builder(window, blend)
            r = evaluate_predictor(
                f"bias_correct(w={window},b={blend})", predict_fn, db, last_n, top_k, alpha, dist_fn
            )
            if r.get("error"):
                continue
            trials.append(r)
            if best is None or r["exact_rate"] > best["exact_rate"]:
                best = r
    p0 = top_k / 1000.0
    if best is not None:
        best_beats = best["exceeds_baseline_p"] < 0.05 and best["exact_rate"] > p0
    else:
        best_beats = False
    return {
        "trials": trials,
        "best": best,
        "best_beats_baseline": best_beats,
        "baseline_expected_rate": p0,
        "note": (
            "修偏改进尝试：遍历窗口/混合系数寻找最优偏置修正方案；"
            "即便最优者亦未稳定、显著超越均匀随机基线。"
            if not best_beats else
            "修偏改进尝试：发现疑似超越基线的方案，需经多重比较与盲评复核后才能进入正式预测。"
        ),
    }


# ---------------------------------------------------------------------------
# Arena orchestration
# ---------------------------------------------------------------------------
def _import_arena():
    try:
        from . import arena_models
    except ImportError:
        import arena_models  # type: ignore
    return arena_models


def collect_schemes() -> list[PredictorSpec]:
    """Old REGISTRY family (8) + new structurally-diverse arena family (4)."""
    import models_sd3d

    arena_models = _import_arena()
    schemes: list[PredictorSpec] = []
    # wrap existing REGISTRY methods (tag by name for the diversity table)
    for spec in models_sd3d.REGISTRY:
        fam = _family_of(spec.name)
        schemes.append(
            PredictorSpec(
                name=spec.name,
                description=spec.description,
                family=fam,
                predict=spec.predict,
                distribution=spec.distribution,
            )
        )
    # new diverse challengers (dicts -> PredictorSpec)
    for d in arena_models.ARENA:
        schemes.append(
            PredictorSpec(
                name=d["name"],
                description=d.get("description", ""),
                family=d.get("family", "arena"),
                predict=d["predict"],
                distribution=d.get("distribution"),
            )
        )
    return schemes


def _family_of(name: str) -> str:
    if name == "uniform_baseline":
        return "均匀基线"
    if "markov" in name:
        return "马尔可夫族"
    if "laplace" in name or "recent" in name:
        return "平滑频率族"
    if "position_frequency" in name:
        return "位置频率族"
    return "频率族"


def run_arena(db: Path, last_n: int = 300, top_k: int = 10, alpha: float = 0.1) -> dict:
    schemes = collect_schemes()
    results = []
    for spec in schemes:
        try:
            r = evaluate_predictor(
                spec.name, spec.predict, db, last_n, top_k, alpha, spec.distribution
            )
        except Exception as exc:  # defensive: one bad scheme must not kill the arena
            r = {"name": spec.name, "error": str(exc)}
        r["family"] = spec.family
        r["description"] = spec.description
        results.append(r)

    # honest headline
    comparable = [r for r in results if not r.get("error") and r["name"] != "uniform_baseline"]
    no_diff = [r for r in comparable if r["verdict"] == "与随机基线无显著差异"]
    better = [r for r in comparable if r["verdict"] == "显著优于随机基线"]
    worse = [r for r in comparable if r["verdict"] == "显著劣于随机基线"]

    # Multiple-comparison control: the 'better' verdict uses raw two-sided p<0.05,
    # but across many schemes some false positives are expected. Apply BH (FDR=0.05)
    # on the right-tail "beats-baseline" p-values to see what survives.
    pvals = [r["exceeds_baseline_p"] for r in comparable]
    fdr_rej = benjamini_hochberg(pvals, q=0.05)
    fdr_better = [r for r, rej in zip(comparable, fdr_rej) if rej and r["exact_rate"] > r["expected_exact_rate"]]

    if len(better) > 0 and len(fdr_better) == 0:
        fdr_note = (
            f"原 {len(better)} 个'显著优于基线'的方案，经 Benjamini-Hochberg 多重比较校正(FDR=0.05)后"
            f"均未能存活——在 {len(comparable)} 次检验中属随机波动，非稳定可预测信号。"
        )
    elif len(fdr_better) > 0:
        fdr_note = (
            f"经 FDR 校正后仍有 {len(fdr_better)} 个方案疑似超越基线，需盲评与多重比较复核后才能进入正式预测（宪章第十条）。"
        )
    else:
        fdr_note = "经多重比较校正后，无任何方案超越均匀随机基线。"

    # improvement sweep on the bias-correction challenger
    arena_models = _import_arena()

    sweep = improvement_sweep(
        db,
        lambda w, b: arena_models.bias_correct_builder(w, b),
        last_n=min(last_n, 200),
        top_k=top_k,
        alpha=alpha,
    )

    report = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(timespec="seconds"),
        "config": {"last_n": last_n, "top_k": top_k, "alpha": alpha},
        "theoretical": {
            "baseline_exact_rate": top_k / 1000.0,
            "baseline_position_top1_rate": 0.10,
            "theoretical_log_loss": THEORETICAL_LOG_LOSS,
        },
        "schemes_tested": len(comparable),
        "honesty_layer": {
            "baseline_exact_rate_pct": round(top_k / 1000.0 * 100, 3),
            "theoretical_log_loss": round(THEORETICAL_LOG_LOSS, 4),
            "no_significant_difference": len(no_diff),
            "significantly_better_raw": len(better),
            "significantly_worse_raw": len(worse),
            "significantly_better_fdr": len(fdr_better),
            "fdr_note": fdr_note,
            "headline": (
                f"在 {len(comparable)} 个候选方案中，{len(no_diff)} 个与均匀随机基线无显著差异；"
                f"{len(better)} 个原始显著优于基线（FDR校正后 {len(fdr_better)} 个）；"
                f"{len(worse)} 个显著劣于基线（同为随机波动）。"
            ),
            "conclusion": (
                "命中率与随机无异：没有任何候选方案能在多重比较校正后稳定、显著地超越均匀随机基线。"
                if len(fdr_better) == 0 else
                "存在经校正后仍疑似超越基线的方案，需经盲评复核后才能进入正式预测（宪章第十条）。"
            ),
        },
        "results": results,
        "improvement_sweep": sweep,
        "disclaimer": (
            "模型竞技场是严格时间前向的假设检验擂台，非可预测性证明；"
            "所有方案均仅使用目标期之前的数据。结论以数据为准，不构成投注建议。"
        ),
    }
    return report


def write_report(report: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="模型竞技场：严格时间前向诚实回测")
    base = Path(__file__).parent
    ap.add_argument("--db", type=Path, default=base.parent / "sd3d_history.sqlite3")
    ap.add_argument("--last-n", type=int, default=300)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--out", type=Path, default=base.parent / "reports" / "predictive-arena-latest.json")
    args = ap.parse_args()

    report = run_arena(args.db, args.last_n, args.top_k, args.alpha)
    write_report(report, args.out)
    print(f"模型竞技场完成: 测试 {report['schemes_tested']} 个方案")
    print(f"诚实层结论: {report['honesty_layer']['conclusion']}")
    print(f"报告: {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
