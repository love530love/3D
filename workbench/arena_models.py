"""Structurally-diverse challenger models for the 模型竞技场 (arena).

These supplement the 8 same-family frequency methods in ``models_sd3d.REGISTRY``
with *genuinely different* structural families, so the "多元描述性对照" is not a
comparison of near-relatives:

  * joint_trigram_frequency  — scores whole 3-digit numbers by their JOINT empirical
                              frequency (not the product of three per-position
                              marginals). Structurally a full 1000-state table.
  * sum_conditioned_frequency — first picks the most likely 和值 (sum), then ranks
                              digits *within that sum bucket*. Conditions on a
                              derived scalar feature.
  * mean_reversion_bias_corrector — assumes the process reverts to its mean and
                              predicts the digits with the largest recent deficit
                              vs the uniform expectation (a classic, testable
                              bias-correction hypothesis; the "fix via backtest"
                              direction).
  * ml_logistic_teaching     — a from-scratch per-position multinomial logistic
                              regression on lag features, strict expanding-window
                              trained. Pure teaching artifact; it will *not* beat
                              the baseline, and the arena shows that honestly.

All predictors conform to the REGISTRY contract:
    predict(train: list[str], top_k: int) -> list[str]   # 3-digit zero-padded
    distribution(train, position, alpha) -> list[float] len 10, ~sums to 1
"""

from __future__ import annotations

import math
from collections import Counter
from itertools import product

from model_screening import ALL_NUMBERS

# ---------------------------------------------------------------------------
# 1) Joint trigram (whole-number) frequency
# ---------------------------------------------------------------------------
def joint_predict(train: list[str], top_k: int) -> list[str]:
    counts = Counter(train)
    ranked = sorted(ALL_NUMBERS, key=lambda n: (-counts.get(n, 0), n))
    return ranked[:top_k]


def joint_distribution(train: list[str], position: int, alpha: float) -> list[float]:
    counts = Counter(number[position] for number in train)
    denom = len(train) + 10 * alpha
    return [(counts.get(str(d), 0) + alpha) / denom for d in range(10)]


# ---------------------------------------------------------------------------
# 2) Sum-conditioned frequency
# ---------------------------------------------------------------------------
def _sum(n: str) -> int:
    return sum(int(c) for c in n)


def sum_conditioned_predict(train: list[str], top_k: int) -> list[str]:
    sums = Counter(_sum(n) for n in train)
    best_sum = max(sums, key=lambda s: sums[s])
    bucket_counts = Counter(n for n in train if _sum(n) == best_sum)
    ranked = sorted(bucket_counts, key=lambda n: (-bucket_counts[n], n))
    # backfill from global frequency if the bucket is short
    if len(ranked) < top_k:
        g = Counter(train)
        extra = sorted(g, key=lambda n: (-g[n], n))
        seen = set(ranked)
        for n in extra:
            if n not in seen:
                ranked.append(n)
                seen.add(n)
            if len(ranked) >= top_k:
                break
    return [f"{int(n):03d}" for n in ranked[:top_k]]


def sum_conditioned_distribution(train: list[str], position: int, alpha: float) -> list[float]:
    sums = Counter(_sum(n) for n in train)
    best_sum = max(sums, key=lambda s: sums[s])
    bucket = [n for n in train if _sum(n) == best_sum]
    counts = Counter(number[position] for number in bucket)
    denom = len(bucket) + 10 * alpha
    return [(counts.get(str(d), 0) + alpha) / denom for d in range(10)]


# ---------------------------------------------------------------------------
# 3) Mean-reversion / bias-correction predictor
# ---------------------------------------------------------------------------
def _mean_reversion_rank(train: list[str], window: int, blend: float):
    """Return per-position ranked digit lists (most-deficit first) and the
    corrected probability vectors used for the distribution."""
    recent = train[-window:] if len(train) > window else train
    per_pos_freq = []
    for pos in range(3):
        counts = Counter(n[pos] for n in recent)
        total = len(recent) or 1
        freq = {d: counts.get(str(d), 0) / total for d in range(10)}
        per_pos_freq.append(freq)
    rank_pos = []
    corrected = []
    for pos in range(3):
        # largest deficit (expected 0.1 - observed) first
        r = sorted(range(10), key=lambda d: (per_pos_freq[pos][d] - 0.1, d))
        rank_pos.append([str(d) for d in r])
        raw = [(per_pos_freq[pos][d] + 0.0) for d in range(10)]
        # blend observed (normalized) with uniform 0.1
        s = sum(raw) or 1.0
        raw_n = [v / s for v in raw]
        corr = [blend * raw_n[d] + (1 - blend) * 0.1 for d in range(10)]
        corrected.append(corr)
    return rank_pos, corrected


def mean_reversion_predict(train: list[str], top_k: int, window: int = 200, blend: float = 0.5) -> list[str]:
    rank_pos, _ = _mean_reversion_rank(train, window, blend)
    top = 3
    combos = product(*[rank_pos[p][:top] for p in range(3)])
    # score = sum of per-position rank index (lower index = larger deficit = preferred)
    scored = []
    for combo in combos:
        idx = sum(rank_pos[p].index(combo[p]) for p in range(3))
        scored.append((idx, combo))
    scored.sort(key=lambda x: x[0])
    return ["".join(c) for _, c in scored[:top_k]]


def mean_reversion_distribution(train: list[str], position: int, alpha: float, window: int = 200, blend: float = 0.5) -> list[float]:
    _, corrected = _mean_reversion_rank(train, window, blend)
    return corrected[position]


def bias_correct_builder(window: int, blend: float):
    """Factory used by the improvement sweep: returns (predict_fn, dist_fn)."""

    def predict(train, top_k):
        return mean_reversion_predict(train, top_k, window=window, blend=blend)

    def distribution(train, position, alpha):
        return mean_reversion_distribution(train, position, alpha, window=window, blend=blend)

    return predict, distribution


# ---------------------------------------------------------------------------
# 4) ML teaching: per-position multinomial logistic regression (from scratch)
# ---------------------------------------------------------------------------
_ML_WINDOW = 250  # bound the training set so per-target cost is predictable
_ML_STEPS = 40

# Train once per (train list) and reuse for both predict() and distribution()
# within a single target evaluation — the same `train` object is passed to both.
_ML_CACHE: dict = {}


def _features_for(train: list[str], pos: int, L: int = 3, ml_window: int = _ML_WINDOW):
    """X[i] = feature vector for the draw at index i (using L previous draws at
    `pos` as context), Y[i] = digit at `pos`. Only the most recent `ml_window`
    samples are used (bounded cost)."""
    X, Y = [], []
    N = len(train)
    if N < L + 2:
        return X, Y
    windowed = train[-ml_window:] if len(train) > ml_window else train
    base = len(train) - len(windowed)
    for i in range(L, len(windowed)):
        ctx = [int(windowed[i - j - 1][pos]) for j in range(L)]
        recent_mean = sum(ctx) / L
        prev_sum = _sum(windowed[i - 1])
        feat = [d / 9.0 for d in ctx] + [recent_mean / 9.0, prev_sum / 27.0, (base + i) / N]
        X.append(feat)
        Y.append(int(windowed[i][pos]))
    return X, Y


def _train_logistic(X, Y, n_cls: int = 10, steps: int = _ML_STEPS, lr: float = 0.4):
    if not X:
        return None
    n_feat = len(X[0])
    W = [[0.0] * n_feat for _ in range(n_cls)]
    n = len(X)
    for _ in range(steps):
        for i in range(n):
            scores = [sum(W[c][f] * X[i][f] for f in range(n_feat)) for c in range(n_cls)]
            m = max(scores)
            exps = [math.exp(s - m) for s in scores]
            ssum = sum(exps) or 1e-12
            probs = [e / ssum for e in exps]
            for c in range(n_cls):
                err = probs[c] - (1.0 if Y[i] == c else 0.0)
                for f in range(n_feat):
                    W[c][f] -= (lr / n) * err * X[i][f]
    return W


def _probs(W, feat):
    scores = [sum(W[c][f] * feat[f] for f in range(len(feat))) for c in range(len(W))]
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    ssum = sum(exps) or 1e-12
    return [e / ssum for e in exps]


def _context_features(train: list[str], pos: int, L: int = 3):
    ctx = [int(train[-j - 1][pos]) for j in range(L)]
    recent_mean = sum(ctx) / L
    prev_sum = _sum(train[-1]) if train else 13
    return [d / 9.0 for d in ctx] + [recent_mean / 9.0, prev_sum / 27.0, 1.0]


def _get_Ws(train: list[str], L: int = 3):
    key = id(train)
    if key in _ML_CACHE:
        return _ML_CACHE[key]
    Ws = [_train_logistic(*_features_for(train, p, L)) for p in range(3)]
    if len(_ML_CACHE) > 64:
        _ML_CACHE.clear()
    _ML_CACHE[key] = Ws
    return Ws


def ml_logistic_predict(train: list[str], top_k: int, L: int = 3) -> list[str]:
    Ws = _get_Ws(train, L)
    if Ws[0] is None:
        return [f"{n:03d}" for n in range(min(top_k, 1000))]
    feats = [_context_features(train, p, L) for p in range(3)]
    probs = [_probs(Ws[p], feats[p]) for p in range(3)]
    top = 4
    rank_pos = [
        [str(d) for d in sorted(range(10), key=lambda d: (-probs[p][d], d))[:top]]
        for p in range(3)
    ]
    combos = product(*rank_pos)
    scored = sorted(
        combos,
        key=lambda c: -sum(math.log(probs[p][int(c[p])] + 1e-12) for p in range(3)),
    )
    return ["".join(c) for c in scored[:top_k]]


def ml_logistic_distribution(train: list[str], position: int, alpha: float, L: int = 3) -> list[float]:
    Ws = _get_Ws(train, L)
    if Ws[position] is None:
        return [0.1] * 10
    return _probs(Ws[position], _context_features(train, position, L))


# ---------------------------------------------------------------------------
# Registry of arena challengers
# ---------------------------------------------------------------------------
import math  # noqa: E402  (used above in ml_logistic; kept here for clarity)

ARENA = [
    {
        "name": "joint_trigram_frequency",
        "description": "联合整体频率：把 3 位数字作为整体统计联合频率（非三位乘积）。",
        "family": "联合整体族",
        "predict": joint_predict,
        "distribution": joint_distribution,
    },
    {
        "name": "sum_conditioned_frequency",
        "description": "和值条件频率：先取最可能和值，再在该和值桶内排序各位数字。",
        "family": "和值条件族",
        "predict": sum_conditioned_predict,
        "distribution": sum_conditioned_distribution,
    },
    {
        "name": "mean_reversion_bias_corrector",
        "description": "修偏/均值回归残差：预测近期相对均匀期望偏离最大（欠出）的数字（可检验的偏置修正假设）。",
        "family": "修偏均值回归族",
        "predict": lambda train, top_k: mean_reversion_predict(train, top_k),
        "distribution": lambda train, pos, alpha: mean_reversion_distribution(train, pos, alpha),
    },
    {
        "name": "ml_logistic_teaching",
        "description": "ML 教学演示：逐位多项逻辑回归（纯stdlib梯度下降，滞后特征），严格扩展窗口训练。诚实展示仍无法超越基线。",
        "family": "ML逻辑回归族",
        "predict": ml_logistic_predict,
        "distribution": ml_logistic_distribution,
    },
]
