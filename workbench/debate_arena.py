"""双阵营对抗辩论擂台 (Debate Arena) — 正方(可预测派) vs 反方(科学随机派).

This module turns the "模型竞技场" honest backtest into an *adversarial debate*:
  * 正方 (Pro-Predictable camp)  — a manifest of every human "lottery is predictable"
    belief, each turned into a runnable prediction experiment.
  * 反方 (Scientific-Random camp) — a full statistical *weapons arsenal* of
    randomness / non-uniformity tests used to audit any 正方 claim.

Both camps exhaust all means: 正方 runs every strategy as a strict time-forward
backtest; 反方 audits each with the arsenal + Benjamini-Hochberg FDR; 正方 then
evolves (tunes windows / shrinks toward uniform) and re-challenges; the loop
converges. The result is an honest bias-summary: who wins, and whether any
"signal" is statistically real AND practically exploitable.

Charter-compliant by construction:
  * Article 1  — the debate tests randomness; it never assumes predictability.
  * Article 2  — read-only over the authoritative DB.
  * Article 10 — every claim is compared against the uniform random baseline with
    an exact test; a claim only "wins" if it survives FDR AND is profitable after
    costs (statistical significance != practical exploitability).

All statistics are pure standard library (no scipy).
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WB = Path(__file__).resolve().parent
for _p in (str(ROOT), str(WB)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from predictive_eval import (  # noqa: E402
    evaluate_predictor,
    benjamini_hochberg,
    binom_pmf,
    binom_sf,
    binom_two_sided,
    load_numbers,
    THEORETICAL_LOG_LOSS,
)
import arena_models  # noqa: E402
from model_screening import ALL_NUMBERS  # noqa: E402

REPORTS = ROOT / "reports"


# ===========================================================================
# 反方·统计武器库 (Scientific-Random camp weapons arsenal)
# ===========================================================================
def _gammainc_reg(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x) via series / continued fraction."""
    if x <= 0.0:
        return 0.0
    gln = math.lgamma(a)
    if x < a + 1.0:
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(1000):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 1e-12:
                break
        return total * math.exp(-x + a * math.log(x) - gln)
    # continued fraction for the upper tail, then P = 1 - Q
    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    upper = math.exp(-x + a * math.log(x) - gln) * h
    return 1.0 - upper


def chi2_sf(x: float, df: float) -> float:
    """Survival function of chi-square with df degrees of freedom (pure stdlib)."""
    if x <= 0.0:
        return 1.0
    return 1.0 - _gammainc_reg(df / 2.0, x / 2.0)


def norm_sf(z: float) -> float:
    """Two-tailed survival P(|Z| >= |z|) for standard normal via erfc."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def _multinomial_gof(series: list[int]) -> tuple[float, float, str]:
    n = len(series)
    counts = Counter(series)
    expected = n / 10.0
    chi2 = sum((counts.get(d, 0) - expected) ** 2 / expected for d in range(10))
    p = chi2_sf(chi2, 9.0)
    rej = p < 0.05
    interp = (
        f"卡方拟合优度 χ²={chi2:.1f}, p={p:.3f} → 分布{'非均匀' if rej else '未拒绝均匀'}"
    )
    return chi2, p, interp


def _runs_test(series: list[int]) -> tuple[float, float, str]:
    seq = [1 if series[i] > series[i - 1] else 0 for i in range(1, len(series))]
    n1 = sum(seq)
    n2 = len(seq) - n1
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0, "游程检验：序列单调，无法检验"
    runs = 1
    for i in range(1, len(seq)):
        if seq[i] != seq[i - 1]:
            runs += 1
    exp = 1.0 + 2.0 * n1 * n2 / (n1 + n2)
    var = 2.0 * n1 * n2 * (2.0 * n1 * n2 - n1 - n2) / ((n1 + n2) ** 2 * (n1 + n2 - 1))
    if var <= 0:
        return 0.0, 1.0, "游程检验：方差异常"
    z = (runs - exp) / math.sqrt(var)
    p = norm_sf(z)
    rej = p < 0.05
    interp = (
        f"游程检验 R={runs}, Z={z:.2f}, p={p:.3f} → 顺序{'聚簇/趋势' if rej else '随机'}"
    )
    return z, p, interp


def _serial_autocorr(series: list[int], lag: int) -> tuple[float, float, str]:
    n = len(series) - lag
    if n < 3:
        return 0.0, 1.0, f"自相关(lag{lag})：样本不足"
    xs = [float(series[i]) for i in range(len(series) - lag)]
    ys = [float(series[i + lag]) for i in range(len(series) - lag)]
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / n
    vx = sum((xs[i] - mx) ** 2 for i in range(n)) / n
    vy = sum((ys[i] - my) ** 2 for i in range(n)) / n
    if vx <= 0 or vy <= 0:
        return 0.0, 1.0, f"自相关(lag{lag})：方差为零"
    r = cov / math.sqrt(vx * vy)
    if abs(r) >= 1.0:
        r = 0.999 if r > 0 else -0.999
    t = r * math.sqrt((n - 2) / (1 - r * r))
    p = norm_sf(t)
    rej = p < 0.05
    interp = (
        f"滞后自相关(lag{lag}) r={r:.3f}, p={p:.3f} → {'存在线性依赖' if rej else '无显著自相关'}"
    )
    return r, p, interp


def _entropy_test(digits: list[int], k: int = 300) -> tuple[float, float, str]:
    n = len(digits)
    counts = Counter(digits)
    obs = -sum((c / n) * math.log(c / n) for c in counts.values() if c > 0)
    max_h = math.log(10.0)
    # null: draw n uniform digits k times, record entropy, one-sided p
    below = 0
    for _ in range(k):
        sim = [random.randint(0, 9) for _ in range(n)]
        c = Counter(sim)
        h = -sum((v / n) * math.log(v / n) for v in c.values() if v > 0)
        if h <= obs:
            below += 1
    p = (below + 1) / (k + 1)
    rej = p < 0.05
    norm = obs / max_h
    interp = (
        f"信息熵 H={obs:.3f} (归一 {norm:.3f}), 置换p={p:.3f} → "
        f"{'比均匀更可压缩' if rej else '接近最大熵'}"
    )
    return obs, p, interp


def _ljung_box(series: list[int], lags: int = 10) -> tuple[float, float, str]:
    n = len(series)
    mean = sum(series) / n
    # autocorrelations
    acf = []
    for k in range(1, lags + 1):
        num = sum((series[i] - mean) * (series[i - k] - mean) for i in range(k, n))
        den = sum((series[i] - mean) ** 2 for i in range(n))
        acf.append(num / den if den else 0.0)
    Q = n * (n + 2) * sum(acf[k] ** 2 / (n - k - 1) for k in range(lags))
    p = chi2_sf(Q, lags)
    rej = p < 0.05
    interp = f"Ljung-Box Q={Q:.1f}, p={p:.3f} → {'存在序列相关' if rej else '无显著序列相关'}"
    return Q, p, interp


def _max_run_test(series: list[int], n_sim: int = 1500) -> tuple[float, float, str]:
    n = len(series)
    obs = 1
    cur = 1
    for i in range(1, n):
        if series[i] == series[i - 1]:
            cur += 1
            obs = max(obs, cur)
        else:
            cur = 1
    ge = 0
    for _ in range(n_sim):
        sim = [random.randint(0, 9) for _ in range(n)]
        m = 1
        c = 1
        for i in range(1, n):
            if sim[i] == sim[i - 1]:
                c += 1
                m = max(m, c)
            else:
                c = 1
        if m >= obs:
            ge += 1
    p = (ge + 1) / (n_sim + 1)
    rej = p < 0.05
    interp = (
        f"最大连号长度={obs}, 模拟p={p:.3f} → {'异常长连号' if rej else '连号长度正常'}"
    )
    return float(obs), p, interp


def _structural_break_test(series: list[int], n_sim: int = 1500) -> tuple[float, float, str]:
    n = len(series)
    cusum = 0.0
    mx = 0.0
    for x in series:
        cusum += x - 4.5
        mx = max(mx, abs(cusum))
    ge = 0
    for _ in range(n_sim):
        cs = 0.0
        m = 0.0
        for _ in range(n):
            cs += random.randint(0, 9) - 4.5
            m = max(m, abs(cs))
        if m >= mx:
            ge += 1
    p = (ge + 1) / (n_sim + 1)
    rej = p < 0.05
    interp = (
        f"CUSUM最大偏移={mx:.1f}, 模拟p={p:.3f} → {'存在结构断点/漂移' if rej else '平稳无漂移'}"
    )
    return mx, p, interp


def run_arsenal(db: Path) -> dict:
    """Run the full 反方 arsenal once over the historical digit series."""
    nums = load_numbers(db)
    if not nums:
        return {"tests": [], "n_tests": 0, "n_rejected": 0, "summary": "无数据"}
    series3 = [[int(num[p]) for (_, num) in nums] for p in range(3)]
    pos_names = ["百位", "十位", "个位"]
    tests: list[dict] = []
    for p in range(3):
        s = series3[p]
        checks = [
            ("卡方拟合优度", _multinomial_gof(s)),
            ("游程检验", _runs_test(s)),
            ("滞后自相关(lag1)", _serial_autocorr(s, 1)),
            ("滞后自相关(lag2)", _serial_autocorr(s, 2)),
            ("信息熵", _entropy_test(s)),
            ("Ljung-Box(10)", _ljung_box(s)),
            ("最大连号", _max_run_test(s)),
            ("结构断点CUSUM", _structural_break_test(s)),
        ]
        for name, (stat, pval, interp) in checks:
            tests.append(
                {
                    "position": pos_names[p],
                    "name": name,
                    "stat": round(stat, 4) if isinstance(stat, float) else stat,
                    "p": round(pval, 4),
                    "rejects": bool(pval < 0.05),
                    "interpretation": interp,
                }
            )
    n_rej = sum(1 for t in tests if t["rejects"])
    if n_rej == 0:
        summary = (
            f"反方武器库对 3 个位置共运行 {len(tests)} 项随机性检验，"
            f"0 项拒绝'均匀'假设——序列在统计上与均匀随机无法区分。"
        )
    else:
        summary = (
            f"反方武器库共运行 {len(tests)} 项检验，{n_rej} 项在 α=0.05 下出现微弱偏离均匀，"
            f"但这只说明'非均匀'，不等于'可被策略利用'；最终是否可盈利仍需盈利性检验佐证。"
        )
    return {"tests": tests, "n_tests": len(tests), "n_rejected": n_rej, "summary": summary}


# ===========================================================================
# 正方·主张与策略清单 (Pro-Predictable camp manifest)
# ===========================================================================
def _recent(train: list[str], window):
    return train[-window:] if window else train


def _pos_freq(train: list[str], window):
    rec = _recent(train, window)
    return [Counter(n[p] for n in rec) for p in range(3)]


def _top_digits(freqs, pos: int, top: int) -> list[str]:
    items = sorted(freqs[pos].items(), key=lambda kv: (-kv[1], int(kv[0])))
    return [str(d) for d, _ in items[:top]]


def _joint(train: list[str]) -> Counter:
    return Counter(train)


def _pad(train: list[str], joint: Counter, res: list[str], top_k: int) -> list[str]:
    if len(res) >= top_k:
        return res[:top_k]
    seen = set(res)
    for n in sorted(ALL_NUMBERS, key=lambda x: (-joint.get(x, 0), x)):
        if n not in seen:
            res.append(n)
            seen.add(n)
            if len(res) >= top_k:
                break
    return res[:top_k]


def _combine(train: list[str], pos_digits: list[list[str]], top_k: int) -> list[str]:
    joint = _joint(train)
    combos = list(product(*pos_digits))
    scored = sorted(combos, key=lambda c: (-joint.get("".join(c), 0), "".join(c)))
    res = ["".join(c) for c in scored]
    return _pad(train, joint, res, top_k)


def _filter_combine(train: list[str], filt, top_k: int) -> list[str]:
    joint = _joint(train)
    cands = [n for n in ALL_NUMBERS if filt(n)]
    cands.sort(key=lambda n: (-joint.get(n, 0), n))
    return _pad(train, joint, cands, top_k)


def _dist_recent(window):
    def d(train, pos, alpha):
        rec = _recent(train, window)
        cnt = Counter(n[pos] for n in rec)
        denom = len(rec) + 10 * alpha
        return [(cnt.get(str(d), 0) + alpha) / denom for d in range(10)]

    return d


def _dist_full():
    def d(train, pos, alpha):
        cnt = Counter(n[pos] for n in train)
        denom = len(train) + 10 * alpha
        return [(cnt.get(str(d), 0) + alpha) / denom for d in range(10)]

    return d


def _gap_digits(train: list[str], pos: int, descending: bool) -> list[str]:
    last = {d: -1 for d in range(10)}
    for i, n in enumerate(train):
        last[int(n[pos])] = i
    L = len(train)
    gaps = {d: (L - 1 - last[d]) for d in range(10)}
    items = sorted(gaps.items(), key=lambda kv: (-kv[1] if descending else kv[1], kv[0]))
    return [str(d) for d, _ in items[:3]]


def _sum(n: str) -> int:
    return sum(int(c) for c in n)


# --- individual 正方 strategies ------------------------------------------------
def hot_predict(train, top_k):
    freqs = _pos_freq(train, 50)
    pd = [_top_digits(freqs, p, 3) for p in range(3)]
    return _combine(train, pd, top_k)


def cold_predict(train, top_k):
    pd = [_gap_digits(train, p, True) for p in range(3)]
    return _combine(train, pd, top_k)


def gap_predict(train, top_k):
    pd = [_gap_digits(train, p, False) for p in range(3)]
    return _combine(train, pd, top_k)


def sum_value_predict(train, top_k):
    rec = _recent(train, 200)
    sc = Counter(_sum(n) for n in rec)
    best = max(sc, key=lambda s: sc[s])
    return _filter_combine(train, lambda n: _sum(n) == best, top_k)


def sum_tail_predict(train, top_k):
    rec = _recent(train, 200)
    sc = Counter(_sum(n) % 10 for n in rec)
    best = max(sc, key=lambda s: sc[s])
    return _filter_combine(train, lambda n: _sum(n) % 10 == best, top_k)


def span_predict(train, top_k):
    rec = _recent(train, 200)
    spans = Counter(int(max(n)) - int(min(n)) for n in rec)
    best = max(spans, key=lambda s: spans[s])
    return _filter_combine(train, lambda n: int(max(n)) - int(min(n)) == best, top_k)


def parity_predict(train, top_k):
    rec = _recent(train, 200)
    freqs = [Counter(int(n[p]) % 2 for n in rec) for p in range(3)]
    pd = []
    for p in range(3):
        keep = 1 if freqs[p].get(1, 0) >= freqs[p].get(0, 0) else 0
        pd.append([str(d) for d in range(10) if d % 2 == keep])
    return _combine(train, pd, top_k)


PRIMES = {2, 3, 5, 7}


def prime_predict(train, top_k):
    rec = _recent(train, 200)
    freqs = [Counter((int(n[p]) in PRIMES) for n in rec) for p in range(3)]
    pd = []
    for p in range(3):
        keep = freqs[p].get(True, 0) >= freqs[p].get(False, 0)
        pd.append([str(d) for d in range(10) if (d in PRIMES) == keep])
    return _combine(train, pd, top_k)


def consecutive_predict(train, top_k):
    return _filter_combine(
        train, lambda n: any(abs(int(n[i]) - int(n[i + 1])) == 1 for i in range(2)), top_k
    )


def mirror_predict(train, top_k):
    last = train[-1]
    pd = [[str((int(last[p]) + 5) % 10), str(int(last[p]))] for p in range(3)]
    return _combine(train, pd, top_k)


def repeat_predict(train, top_k):
    last = train[-1]
    pd = [[str((int(last[p]) + o) % 10) for o in (-1, 0, 1)] for p in range(3)]
    return _combine(train, pd, top_k)


def trend_predict(train, top_k):
    rec = _recent(train, 80)
    pd = []
    for p in range(3):
        vals = [int(n[p]) for n in rec]
        m1 = sum(vals) / len(vals)
        half = max(1, len(vals) // 2)
        m0 = sum(vals[:half]) / half
        step = 1 if m1 > m0 else -1
        pred = int(round(m1)) + step
        pred %= 10
        pd.append([str((pred + o) % 10) for o in (-1, 0, 1)])
    return _combine(train, pd, top_k)


def clustering_predict(train, top_k):
    mode = Counter(train).most_common(1)[0][0]
    pd = [[str((int(mode[p]) + o) % 10) for o in (-1, 0, 1)] for p in range(3)]
    return _combine(train, pd, top_k)


def _build_pro_claims() -> list[dict]:
    full = _dist_full()
    rec50 = _dist_recent(50)
    rec200 = _dist_recent(200)
    rec80 = _dist_recent(80)
    return [
        {"id": "hot_number", "name": "热号(近期高频)", "family": "频率-近因",
         "belief": "热手效应/近因偏差：近期高频数字会延续",
         "predict": hot_predict, "distribution": rec50},
        {"id": "cold_number", "name": "冷号(最大遗漏)", "family": "频率-遗漏",
         "belief": "赌徒谬误：久未出现的数字必将回补",
         "predict": cold_predict, "distribution": full},
        {"id": "gap_analysis", "name": "间隔活跃号", "family": "频率-间隔",
         "belief": "可得性启发：最近频繁露面的数字更'活跃'",
         "predict": gap_predict, "distribution": full},
        {"id": "sum_value", "name": "和值条件", "family": "派生标量-和值",
         "belief": "聚类错觉：和值存在'热区'",
         "predict": sum_value_predict, "distribution": rec200},
        {"id": "sum_tail", "name": "和尾条件", "family": "派生标量-和尾",
         "belief": "小数定律：和尾分布可被利用",
         "predict": sum_tail_predict, "distribution": rec200},
        {"id": "span", "name": "跨度条件", "family": "派生标量-跨度",
         "belief": "代表性：跨度存在偏好区间",
         "predict": span_predict, "distribution": rec200},
        {"id": "parity", "name": "奇偶偏好", "family": "奇偶质合",
         "belief": "控制错觉：奇偶有规律",
         "predict": parity_predict, "distribution": rec200},
        {"id": "prime", "name": "质合偏好", "family": "奇偶质合",
         "belief": "确认偏误：质数更'幸运'",
         "predict": prime_predict, "distribution": rec200},
        {"id": "consecutive", "name": "连号邻号", "family": "形态-连邻",
         "belief": "聚类错觉：连号会扎堆",
         "predict": consecutive_predict, "distribution": full},
        {"id": "mirror", "name": "镜像号", "family": "锚定-镜像",
         "belief": "锚定效应：以上期±5为'镜像幸运'",
         "predict": mirror_predict, "distribution": full},
        {"id": "repeat_last", "name": "重号锚定", "family": "锚定-重号",
         "belief": "锚定效应：上期数字会重演",
         "predict": repeat_predict, "distribution": full},
        {"id": "trend_following", "name": "趋势外推", "family": "趋势",
         "belief": "代表性：走势会延续",
         "predict": trend_predict, "distribution": rec80},
        {"id": "clustering", "name": "聚簇中心", "family": "形态-聚簇",
         "belief": "聚类错觉：以众数号为中心聚集",
         "predict": clustering_predict, "distribution": full},
        {"id": "mean_reversion", "name": "均值回归修偏", "family": "修偏-均值回归",
         "belief": "均值回归：偏离均匀者将回归",
         "predict": arena_models.mean_reversion_predict,
         "distribution": arena_models.mean_reversion_distribution},
        {"id": "ml_features", "name": "ML特征逻辑回归", "family": "ML-教学",
         "belief": "特征工程+梯度下降可学到隐藏结构（教学演示）",
         "predict": arena_models.ml_logistic_predict,
         "distribution": arena_models.ml_logistic_distribution},
    ]


# ===========================================================================
# 评估增强：效应量 / 贝叶斯因子 / 安慰剂 / 可复现性
# ===========================================================================
def _cohens_h(p1: float, p0: float) -> float:
    p1 = min(max(p1, 0.0), 1.0)
    p0 = min(max(p0, 0.0), 1.0)
    return 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p0))


def _odds_ratio(p1: float, p0: float) -> float:
    a = p1 / (1 - p1) if p1 < 1 else 1e6
    b = p0 / (1 - p0) if p0 < 1 else 1e6
    return a / b


def _bayes_factor(k: int, n: int, p0: float) -> float:
    if n <= 0 or k <= 0 or k >= n:
        return 0.0
    p_hat = k / n
    return binom_pmf(k, n, p_hat) / max(binom_pmf(k, n, p0), 1e-300)


def _quick_eval(nums: list[tuple[int, str]], predict, dist, top_k: int, alpha: float) -> dict | None:
    if len(nums) <= 2:
        return None
    exact = 0
    n = 0
    for i in range(1, len(nums)):
        train = [nums[j][1] for j in range(i)]
        if len(train) < 2:
            continue
        cands = predict(train, top_k) or []
        if nums[i][1] in cands:
            exact += 1
        n += 1
    if n == 0:
        return None
    p0 = top_k / 1000.0
    return {
        "exact_rate": exact / n,
        "expected_exact_rate": p0,
        "exceeds_baseline_p": binom_sf(exact, n, p0),
    }


def _placebo_shuffle(claim: dict, db: Path, last_n: int, top_k: int, alpha: float) -> float:
    nums = load_numbers(db)
    if len(nums) <= last_n + 1:
        return 1.0
    start = max(0, len(nums) - last_n)
    work = list(nums)
    tail = [work[i][1] for i in range(start, len(work))]
    random.seed(20260911)
    random.shuffle(tail)
    for idx, i in enumerate(range(start, len(work))):
        work[i] = (work[i][0], tail[idx])
    r = _quick_eval(work, claim["predict"], claim["distribution"], top_k, alpha)
    return r["exceeds_baseline_p"] if r else 1.0


def _split_half_consistent(claim: dict, db: Path, last_n: int, top_k: int, alpha: float) -> bool:
    nums = load_numbers(db)
    if len(nums) <= last_n + 1:
        return True
    start = max(0, len(nums) - last_n)
    window = nums[start:]
    half = max(2, len(window) // 2)
    fh = _quick_eval(window[: half + 1], claim["predict"], claim["distribution"], top_k, alpha)
    sh = _quick_eval(window[half:], claim["predict"], claim["distribution"], top_k, alpha)
    if not fh or not sh:
        return True
    e_fh = fh["exact_rate"] - fh["expected_exact_rate"]
    e_sh = sh["exact_rate"] - sh["expected_exact_rate"]
    return (e_fh >= 0) == (e_sh >= 0)


# ===========================================================================
# 双阵营对抗引擎
# ===========================================================================
class DebateArena:
    def __init__(self, db: Path, last_n: int = 200, top_k: int = 10, alpha: float = 0.1,
                 fdr_q: float = 0.05, max_rounds: int = 4, prize: float = 1040.0,
                 cost: float = 2.0):
        self.db = db
        self.last_n = last_n
        self.top_k = top_k
        self.alpha = alpha
        self.fdr_q = fdr_q
        self.max_rounds = max_rounds
        self.prize = prize
        self.cost = cost
        self.claims = _build_pro_claims()

    def _collect(self, claim: dict, with_extra: bool) -> dict:
        ev = evaluate_predictor(
            claim["name"], claim["predict"], self.db, self.last_n,
            self.top_k, self.alpha, claim["distribution"],
        )
        p0 = ev.get("expected_exact_rate", self.top_k / 1000.0)
        p1 = ev.get("exact_rate", 0.0)
        rec = {
            "claim": claim["id"],
            "name": claim["name"],
            "family": claim["family"],
            "belief": claim["belief"],
            "n": ev.get("n"),
            "exact_rate": p1,
            "expected_exact_rate": p0,
            "two_sided_p": ev.get("two_sided_p"),
            "exceeds_baseline_p": ev.get("exceeds_baseline_p"),
            "verdict": ev.get("verdict"),
            "mean_log_loss": ev.get("mean_log_loss"),
            "effect_size_h": _cohens_h(p1, p0),
            "odds_ratio": _odds_ratio(p1, p0),
            "bayes_factor": _bayes_factor(ev.get("exact_hits", 0), ev.get("n", 0), p0),
            "placebo_exceeds_p": None,
            "placebo_robust": None,
            "split_half_consistent": None,
            "fdr_survivor": False,
            "rejected": True,
            "reject_reason": "",
        }
        # base reject reason from the arena verdict
        if rec["verdict"] == "显著优于随机基线":
            rec["rejected"] = False
            rec["reject_reason"] = "原始检验显著优于基线（待 FDR 与额外闸门复核）"
        else:
            rec["reject_reason"] = "命中率与均匀随机基线无显著差异（原始检验未通过）"
        if with_extra and rec["exceeds_baseline_p"] is not None and rec["exceeds_baseline_p"] < self.alpha:
            rec["placebo_exceeds_p"] = _placebo_shuffle(claim, self.db, self.last_n, self.top_k, self.alpha)
            rec["placebo_robust"] = rec["placebo_exceeds_p"] >= self.alpha
            rec["split_half_consistent"] = _split_half_consistent(claim, self.db, self.last_n, self.top_k, self.alpha)
        return rec

    def _fdr_gate(self, evidences: list[dict]) -> None:
        pvals = [e["exceeds_baseline_p"] for e in evidences if e["exceeds_baseline_p"] is not None]
        idx = [i for i, e in enumerate(evidences) if e["exceeds_baseline_p"] is not None]
        if not pvals:
            return
        rej = benjamini_hochberg(pvals, q=self.fdr_q)
        for j, i in enumerate(idx):
            e = evidences[i]
            if rej[j]:
                e["fdr_survivor"] = True
                e["rejected"] = False
                reason = "通过 FDR 校正，仍显著优于基线"
                if e["placebo_exceeds_p"] is not None:
                    reason += "；" + ("安慰剂稳健" if e["placebo_robust"] else "安慰剂同样显著(伪信号)")
                e["reject_reason"] = reason
            else:
                e["rejected"] = True
                e["reject_reason"] = "原始显著但经 Benjamini-Hochberg FDR 校正后被否（多重比较伪阳性）"

    def run(self) -> dict:
        arsenal = run_arsenal(self.db)
        rounds = []
        all_evidence: list[dict] = []
        survivors = []

        # Round 1 — 正方 出尽全部主张
        r1 = [self._collect(c, with_extra=True) for c in self.claims]
        self._fdr_gate(r1)
        all_evidence.extend(r1)
        survivors = [e for e in r1 if e["fdr_survivor"]]
        rounds.append(self._round_snapshot(1, [e["claim"] for e in r1], survivors, r1))

        # Evolution rounds — 正方 据反馈迭代（调窗/向均匀收缩），反方 再审计
        prev_new = len(survivors)
        for rnd in range(2, self.max_rounds + 1):
            if not survivors:
                break
            evo = self._evolve(survivors)
            if not evo:
                break
            re = [self._collect(c, with_extra=True) for c in evo]
            self._fdr_gate(re)
            all_evidence.extend(re)
            new_surv = [e for e in re if e["fdr_survivor"] and e["claim"] not in {s["claim"] for s in survivors}]
            rounds.append(self._round_snapshot(rnd, [e["claim"] for e in re], new_surv, re))
            survivors.extend(new_surv)
            if len(new_surv) == 0:
                break
            if len(new_surv) >= prev_new and rnd >= 3:
                break
            prev_new = len(new_surv)

        return self._build_report(arsenal, rounds, all_evidence, survivors)

    def _evolve(self, survivors: list[dict]) -> list[dict]:
        """正方 进化：对幸存主张尝试不同回看窗 + 向均匀基线收缩，作为新候补挑战。"""
        evolved = []
        windows = [100, 400]
        for s in survivors:
            base = next(c for c in self.claims if c["id"] == s["claim"])
            for w in windows:
                # 用不同窗口重建分布（仅对支持窗口的策略有意义）
                evo_dist = _dist_recent(w)
                evolved.append({
                    "id": f"{base['id']}__w{w}",
                    "name": f"{base['name']}·窗{w}",
                    "family": base["family"] + "(进化)",
                    "belief": base["belief"] + f"；尝试窗口={w}",
                    "predict": base["predict"],
                    "distribution": evo_dist,
                })
        return evolved

    def _round_snapshot(self, rnd, claims, survivors, evidences) -> dict:
        return {
            "round": rnd,
            "claims": claims,
            "n_claims": len(claims),
            "survivors": [e["claim"] for e in survivors],
            "n_survivors": len(survivors),
            "new_survivors": len([e for e in survivors if e.get("_new")]),
            "verdict": "本轮反方审计完成" + (f"；{len(survivors)} 项主张存活" if survivors else "；无主张存活"),
        }

    def _build_report(self, arsenal, rounds, all_evidence, survivors) -> dict:
        total = len(self.claims)
        # distinct survivor ids (may repeat across rounds)
        survivor_ids = []
        for e in all_evidence:
            if e["fdr_survivor"] and e["claim"] not in survivor_ids:
                survivor_ids.append(e["claim"])
        raw_better = sum(1 for e in all_evidence if e["verdict"] == "显著优于随机基线")
        rejected = sum(1 for e in all_evidence if e["rejected"])

        pro_score = len(survivor_ids) / total if total else 0.0
        anti_score = rejected / total if total else 0.0

        # profitability of best survivor
        best = None
        profit_per_bet = None
        for e in all_evidence:
            if e["fdr_survivor"]:
                edge = e["exact_rate"] - e["expected_exact_rate"]
                ppb = e["exact_rate"] * self.prize - self.top_k * self.cost
                if best is None or e["exact_rate"] > best["exact_rate"]:
                    best = e
                    profit_per_bet = ppb
                if e is best:
                    profit_per_bet = ppb

        # dual-axis gauge
        believability = pro_score
        statistical_strength = anti_score
        radar = {
            "命中率边缘": round(min(1.0, (best["exact_rate"] / best["expected_exact_rate"]) - 1.0) if best else 0.0, 3),
            "FDR存活": round(pro_score, 3),
            "可盈利性": 1.0 if (profit_per_bet is not None and profit_per_bet > 0) else 0.0,
            "可复现": round(
                sum(1 for e in all_evidence if e.get("split_half_consistent")) /
                max(1, sum(1 for e in all_evidence if e.get("split_half_consistent") is not None)), 3
            ),
            "安慰剂稳健": round(
                sum(1 for e in all_evidence if e.get("placebo_robust")) /
                max(1, sum(1 for e in all_evidence if e.get("placebo_robust") is not None)), 3
            ),
        }

        winner, conclusion = self._final_verdict(len(survivor_ids), profit_per_bet, best)

        fdr_note = (
            f"经 Benjamini-Hochberg 多重比较校正(FDR={self.fdr_q})后，"
            f"{len(survivor_ids)}/{total} 项主张稳定、显著超越均匀随机基线；"
            f"其余 {total - len(survivor_ids)} 项均被反方武器库驳回。"
        )
        disclaimer = (
            "本辩论擂台为假设检验演示，不构成任何投注建议。福彩3D 开奖为受监管随机过程；"
            "即使个别策略统计显著，也须扣除成本后仍盈利方可实用（统计显著 ≠ 实战可盈利）。"
        )

        return {
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "config": {
                "last_n": self.last_n, "top_k": self.top_k, "alpha": self.alpha,
                "max_rounds": self.max_rounds, "fdr_q": self.fdr_q,
                "prize": self.prize, "cost_per_number": self.cost,
            },
            "scoreboard": {
                "pro_score": round(pro_score, 3),
                "anti_score": round(anti_score, 3),
                "claims_total": total,
                "raw_better": raw_better,
                "survivors_fdr": len(survivor_ids),
                "correct_rejects": rejected,
            },
            "arsenal": arsenal,
            "rounds": rounds,
            "evidence": all_evidence,
            "dual_axis": {
                "believability": round(believability, 3),
                "statistical_strength": round(statistical_strength, 3),
                "radar": radar,
            },
            "final_verdict": {
                "winner": winner,
                "winner_label": {
                    "random": "反方胜 · 纯随机占优",
                    "weak_signal": "存在微弱可预测信号，需进一步验证",
                    "inconclusive": "结论不确定",
                }[winner],
                "profit_per_bet": (round(profit_per_bet, 4) if profit_per_bet is not None else None),
                "best_survivor": (best["claim"] if best else None),
                "conclusion": conclusion,
                "fdr_note": fdr_note,
                "disclaimer": disclaimer,
            },
        }

    def _final_verdict(self, n_survivors, profit_per_bet, best):
        if n_survivors == 0:
            return "random", (
                "反方（科学随机派）在对抗中占优：全部 "
                f"{len(self.claims)} 项'可预测'主张，经精确二项检验 + Benjamini-Hochberg FDR 校正后，"
                "无一稳定、显著超越均匀随机基线。人类关于'热号/冷号/和值/连号/趋势'等执念，"
                "在本数据上均为随机波动。福彩3D 开奖与均匀随机无法区分。"
            )
        if profit_per_bet is not None and profit_per_bet > 0:
            return "weak_signal", (
                f"存在 {n_survivors} 项主张在 FDR 校正后仍显著优于基线，且其扣除成本后的"
                f"每注期望收益为正（¥{profit_per_bet:.2f}）。但样本仍有限，建议扩充数据并盲评复核，"
                "暂不下'可预测'定论。"
            )
        return "inconclusive", (
            f"有 {n_survivors} 项主张统计显著，但扣除投注成本后每注期望收益非正"
            f"（¥{profit_per_bet:.2f}），即'统计显著但不实用'。结论：随机过程占主导，"
            "不存在可盈利的可预测信号。"
        )


def run_debate(db: Path, last_n: int = 200, top_k: int = 10, alpha: float = 0.1,
               fdr_q: float = 0.05, max_rounds: int = 4, prize: float = 1040.0,
               cost: float = 2.0) -> dict:
    arena = DebateArena(db, last_n, top_k, alpha, fdr_q, max_rounds, prize, cost)
    return arena.run()


def write_report(report: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)


def main():
    import argparse

    ap = argparse.ArgumentParser(description="双阵营对抗辩论擂台")
    ap.add_argument("--db", default=str(ROOT / "sd3d_history.sqlite3"))
    ap.add_argument("--last-n", type=int, default=200)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--fdr-q", type=float, default=0.05)
    ap.add_argument("--max-rounds", type=int, default=4)
    ap.add_argument("--prize", type=float, default=1040.0)
    ap.add_argument("--cost", type=float, default=2.0)
    ap.add_argument("--out", default=str(REPORTS / "debate-arena-latest.json"))
    a = ap.parse_args()
    report = run_debate(
        Path(a.db), a.last_n, a.top_k, a.alpha, a.fdr_q, a.max_rounds, a.prize, a.cost
    )
    write_report(report, Path(a.out))
    fv = report["final_verdict"]
    print(f"Wrote {a.out}")
    print(f"正方主张 {report['scoreboard']['claims_total']} 项 · FDR存活 {report['scoreboard']['survivors_fdr']} 项")
    print(f"裁决: {fv['winner_label']}")
    print(f"结论: {fv['conclusion']}")


if __name__ == "__main__":
    main()
