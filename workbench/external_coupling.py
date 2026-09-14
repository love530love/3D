"""外部 / 跨域耦合探针（"蝴蝶效应 / 微妙联结" 的域外延伸，补齐反方盲区）。

前序模块 `structure_tests.py` 已探测**序列内部**的跨位置-时滞耦合与高阶马尔可夫结构，
但从未问过一个更"开放"的问题：**外部世界的状态**（星期、周末、月份、月初/月末）
是否以任何方式与开奖数字分布耦合？这正是用户反复强调的"外部/跨域耦合"——
万一开奖机房的某种外部节律、摇奖安排的日历结构、或人类投注行为的周期性，
在统计上留下了可探测的微弱痕迹呢？本模块用两类严格检验来诚实回答：

  1. 卡方独立性检验：对每个 (位置 × 外部状态) 构造「数字(0..9) × 外部状态水平」列联表，
     检验"数字分布是否独立于外部状态"。
  2. 均值置换检验：对二元外部特征（周末 / 月初 / 月末），比较"该外部状态下某位置数字均值"
     与"其余期"的差异，以标签置换零分布给出严格 p 值。

全部 p 值经 **Benjamini-Hochberg FDR (q=0.05)** 校正；若任何耦合在 FDR 后存活，则
存在可深挖的跨域弱信号空间；若全部未存活，则诚实收窄该方向（但探索不终止）。
宪章兼容：只读权威 DB、时间前向（外部特征仅由开奖日期派生，无任何未来信息泄漏）、
不宣称盈利、对照随机基线。

外部特征仅从每期 `values_json` 的日期字段（如 "2026-09-13"）派生，属"历史已发生"的
确定信息，构造上零泄漏；但须注意：多重比较下"周末某位数字偏高"完全可能由偶然产生，
故以 FDR 为闸门，并以 OOS 复现为后续条件。
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def _chi2_sf(x: float, df: float) -> float:
    """卡方上尾（直接复用 debate_arena 的实现，避免重复依赖漂移）。"""
    from debate_arena import chi2_sf
    return chi2_sf(x, df)


def _benjamini_hochberg(pvals: list[float], q: float = 0.05) -> list[bool]:
    from predictive_eval import benjamini_hochberg
    return benjamini_hochberg(pvals, q)


# ---------------------------------------------------------------------------
# 数据加载：期号 / 三码 / 派生外部特征
# ---------------------------------------------------------------------------
@dataclass
class Draw:
    period: int
    number: str
    weekday: int      # 0=Mon .. 6=Sun
    weekend: bool
    month: int        # 1..12
    month_start: bool # day <= 5
    month_end: bool   # day >= 26


def load_draws(db: Path) -> list[Draw]:
    """读 sqlite3，解析三码并从日期字段派生外部回归量。解析失败的期跳过。"""
    out: list[Draw] = []
    with sqlite3.connect(str(db)) as c:
        rows = c.execute(
            "SELECT period,values_json FROM draws ORDER BY CAST(period AS INTEGER)"
        ).fetchall()
    for period, payload in rows:
        try:
            fields = json.loads(payload)
            number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
            if len(number) != 3:
                continue
            # 日期是 values_json 的最后一个字段（如 "2026-09-13"）
            date_str = str(fields[-1]).strip()
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            continue
        day = dt.day
        wd = dt.weekday()
        out.append(Draw(
            period=int(period), number=number, weekday=wd, weekend=wd >= 5,
            month=dt.month, month_start=day <= 5, month_end=day >= 26,
        ))
    return out


# ---------------------------------------------------------------------------
# 检验 1：卡方独立性（数字 × 外部状态水平）
# ---------------------------------------------------------------------------
def _chi2_independence(digits: list[int], states: list[int]) -> tuple[float, float, int]:
    """列联表 digit(10) × state(k)，返回 (chi2, p, df)。"""
    levels = sorted(set(states))
    k = len(levels)
    sidx = {s: i for i, s in enumerate(levels)}
    obs = [[0] * k for _ in range(10)]
    for d, s in zip(digits, states):
        obs[d][sidx[s]] += 1
    row_tot = [sum(r) for r in obs]
    col_tot = [sum(obs[r][c] for r in range(10)) for c in range(k)]
    N = sum(row_tot)
    if N == 0:
        return 0.0, 1.0, (10 - 1) * (k - 1)
    chi2 = 0.0
    for r in range(10):
        for c in range(k):
            e = row_tot[r] * col_tot[c] / N
            if e > 0:
                chi2 += (obs[r][c] - e) ** 2 / e
    df = (10 - 1) * (k - 1)
    return chi2, _chi2_sf(chi2, df), df


# ---------------------------------------------------------------------------
# 检验 2：均值置换检验（二元外部特征）
# ---------------------------------------------------------------------------
def _mean_permutation(digits: list[int], flags: list[bool], m_perm: int, rnd: random.Random) -> tuple[float, float]:
    """比较 flag=True 组与 flag=False 组的数字均值差；以标签置换零分布给 p。"""
    n = len(digits)
    grp = [digits[i] for i in range(n) if flags[i]]
    oth = [digits[i] for i in range(n) if not flags[i]]
    if not grp or not oth:
        return 0.0, 1.0
    obs = (sum(grp) / len(grp)) - (sum(oth) / len(oth))
    aobs = abs(obs)
    ge = 0
    perm = flags[:]
    for _ in range(m_perm):
        rnd.shuffle(perm)
        g = [digits[i] for i in range(n) if perm[i]]
        o = [digits[i] for i in range(n) if not perm[i]]
        if abs(sum(g) / len(g) - sum(o) / len(o)) >= aobs:
            ge += 1
    p = (ge + 1) / (m_perm + 1)
    return round(obs, 4), p


# ---------------------------------------------------------------------------
# 电池主流程
# ---------------------------------------------------------------------------
def run_battery(db: Path, m_perm: int = 400, seed: int = 20260914) -> dict:
    rnd = random.Random(seed)
    draws = load_draws(db)
    if len(draws) < 50:
        return {"n": len(draws), "tests": [], "summary": "样本不足"}
    n = len(draws)
    pos_names = ["百位", "十位", "个位"]
    digits_by_pos = [
        [int(d.number[0]) for d in draws],
        [int(d.number[1]) for d in draws],
        [int(d.number[2]) for d in draws],
    ]
    raw: list[dict] = []

    # (1) 卡方独立性：外部状态特征 × 位置
    indep_features = [
        ("weekday", "星期", [d.weekday for d in draws]),
        ("month", "月份", [d.month for d in draws]),
    ]
    binary_features = [
        ("weekend", "周末", [d.weekend for d in draws]),
        ("month_start", "月初(≤5日)", [d.month_start for d in draws]),
        ("month_end", "月末(≥26日)", [d.month_end for d in draws]),
    ]
    for feat_key, feat_label, states in indep_features:
        k = len(set(states))
        for p in range(3):
            chi2, pval, df = _chi2_independence(digits_by_pos[p], states)
            raw.append({
                "name": f"独立性 {pos_names[p]}数字 × {feat_label}",
                "type": "chi2_independence", "feature": feat_key, "position": pos_names[p],
                "stat": round(chi2, 3), "df": df, "p": round(pval, 4),
                "rejects_raw": bool(pval < 0.05),
                "interpretation": (
                    f"χ²={chi2:.1f}, df={df}, p={pval:.3f} → "
                    f"{'数字分布依赖于' + feat_label if pval < 0.05 else feat_label + '与数字独立(无耦合)'}"),
            })
    # 二元特征也做独立性（2 水平，df=9）
    for feat_key, feat_label, flags in binary_features:
        states = [1 if f else 0 for f in flags]
        for p in range(3):
            chi2, pval, df = _chi2_independence(digits_by_pos[p], states)
            raw.append({
                "name": f"独立性 {pos_names[p]}数字 × {feat_label}",
                "type": "chi2_independence", "feature": feat_key, "position": pos_names[p],
                "stat": round(chi2, 3), "df": df, "p": round(pval, 4),
                "rejects_raw": bool(pval < 0.05),
                "interpretation": (
                    f"χ²={chi2:.1f}, df={df}, p={pval:.3f} → "
                    f"{'数字分布依赖于' + feat_label if pval < 0.05 else feat_label + '与数字独立(无耦合)'}"),
            })

    # (2) 均值置换检验：二元特征 × 位置
    for feat_key, feat_label, flags in binary_features:
        for p in range(3):
            obs, pval = _mean_permutation(digits_by_pos[p], flags, m_perm, rnd)
            raw.append({
                "name": f"均值置换 {pos_names[p]}数字 · {feat_label} vs 其余",
                "type": "mean_permutation", "feature": feat_key, "position": pos_names[p],
                "stat": obs, "p": round(pval, 4),
                "rejects_raw": bool(pval < 0.05),
                "interpretation": (
                    f"组间均值差={obs:+.3f}, 置换p={pval:.3f} → "
                    f"{'该外部状态下数字均值显著偏移' if pval < 0.05 else '均值无显著偏移'}"),
            })

    # Benjamini-Hochberg FDR 校正（对所有 p）
    pv = [t["p"] for t in raw]
    rej = _benjamini_hochberg(pv, q=0.05)
    for t, r in zip(raw, rej):
        t["fdr_survivor"] = bool(r)

    survivors = [t["name"] for t in raw if t["fdr_survivor"]]
    n_rej = sum(1 for t in raw if t["rejects_raw"])
    if survivors:
        summary = (
            f"外部/跨域耦合电池共 {len(raw)} 项检验，{n_rej} 项原始 p<0.05，"
            f"经 BH-FDR 后 {len(survivors)} 项存活：{survivors}。"
            "存在可深挖的跨域弱信号空间（须在独立样本 + OOS 盲窗上复现，且不得包装成盈利策略）。")
    else:
        summary = (
            f"外部/跨域耦合电池共 {len(raw)} 项检验，{n_rej} 项原始 p<0.05，"
            "但经 Benjamini-Hochberg FDR 校正后**无一存活**。在星期/月份/月初月末维度上，"
            "未检出开奖数字分布与外部日历状态可区分的耦合；该方向被诚实收窄，但探索不终止"
            "（仍可持续追踪其它外部域：节假日、销售峰值、气象等）。")
    return {
        "n": n, "m_perm": m_perm, "seed": seed,
        "external_features_tested": ["weekday", "month", "weekend", "month_start", "month_end"],
        "tests": raw, "n_rejected_raw": n_rej, "fdr_survivors": survivors,
        "summary": summary,
        "disclaimer": (
            "本电池仅探测'外部日历状态→开奖'的统计学耦合，不构成因果、不证明/否认可预测性；"
            "任何存活耦合须经 OOS 盲窗与独立样本复现，且不得包装成盈利策略。"),
    }


def main():
    ap = argparse.ArgumentParser(description="外部/跨域耦合探针")
    ap.add_argument("--db", type=Path, default=ROOT / "sd3d_history.sqlite3")
    ap.add_argument("--permutations", type=int, default=400)
    ap.add_argument("--out", type=Path, default=REPORTS / "external-coupling-latest.json")
    a = ap.parse_args()
    rep = run_battery(a.db, a.permutations)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(rep["summary"])
    print(f"Report: {a.out.resolve()}")


if __name__ == "__main__":
    main()
