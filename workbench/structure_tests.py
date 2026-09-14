"""跨时序"微妙联结"探测电池（针对"万一有隐藏结构呢"的诚实探针，补齐 反方武器库 的盲区）。

`debate_arena.run_arsenal` 已对**单位置**做了完备的随机性检验（拟合优度/游程/滞后自相关/
信息熵/Ljung-Box/最大连号/CUSUM），但它**逐位置独立**检验，从未探测：
  * 跨位置-跨时滞耦合：百位(t) 与 个位(t-1) 之类"事物之间的关系"；
  * 高阶马尔可夫：P(d_t | d_{t-1}, d_{t-2}) 是否比 P(d_t | d_{t-1}) 多携带信息。
这正是用户反复强调的"微妙联结 / 蝴蝶效应 / 事物之间的关系"。本模块用互信息(MI)+
Pearson+高阶马尔可夫 MI 增量来探测，全部以**置换检验**给出严格 p 值，并对全部检验做
Benjamini-Hochberg FDR——若任何联结在 FDR 后存活，则存在可继续深挖的弱信号空间；
若全部未存活，则诚实收窄该方向（但仍不终止探索）。宪章兼容：时间前向、零泄漏、不宣称盈利。
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def _norm_sf(z: float) -> float:
    return 0.5 * (1 - math.erf(abs(z) / math.sqrt(2)))


def load_series(db: Path) -> list[tuple[int, int, int]]:
    import sqlite3
    with sqlite3.connect(db) as c:
        rows = c.execute(
            "SELECT period,values_json FROM draws ORDER BY CAST(period AS INTEGER)"
        ).fetchall()
    out = []
    for _, payload in rows:
        fields = json.loads(payload)
        num = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(num) == 3:
            out.append((int(num[0]), int(num[1]), int(num[2])))
    return out


def _pearson(xs: list[int], ys: list[int]) -> float:
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / n
    vx = sum((xs[i] - mx) ** 2 for i in range(n)) / n
    vy = sum((ys[i] - my) ** 2 for i in range(n)) / n
    if vx <= 0 or vy <= 0:
        return 0.0
    r = cov / math.sqrt(vx * vy)
    return max(-0.999, min(0.999, r))


def _mutual_info(xs: list[int], ys: list[int], bins: int = 10) -> float:
    """互信息 I(X;Y)（10x10 直方图 + Laplace 平滑），捕捉非线性耦合。"""
    n = len(xs)
    jc = [[1.0] * bins for _ in range(bins)]  # +1 smoothing
    for a, b in zip(xs, ys):
        jc[a][b] += 1.0
    # 边际
    px = [sum(row) for row in jc]
    py = [sum(jc[r][c] for r in range(bins)) for c in range(bins)]
    tot = float(n + bins * bins)
    mi = 0.0
    for r in range(bins):
        for c in range(bins):
            pxy = jc[r][c] / tot
            pxx = px[r] / tot
            pyy = py[c] / tot
            mi += pxy * math.log(pxy / (pxx * pyy))
    return mi


def run_battery(db: Path, m_perm: int = 400, seed: int = 20260914) -> dict:
    rnd = random.Random(seed)
    series = load_series(db)
    if len(series) < 50:
        return {"n": len(series), "tests": [], "summary": "样本不足"}
    n = len(series)
    pos = ["百位", "十位", "个位"]
    raw: list[dict] = []

    # (1) 跨位置-跨时滞 Pearson（analytic p）+ 互信息（置换 p）
    for p in range(3):
        for q in range(3):
            for k in (1, 2, 3):
                xt = [series[t][p] for t in range(k, n)]
                yt = [series[t - k][q] for t in range(k, n)]
                r = _pearson(xt, yt)
                tstat = r * math.sqrt((len(xt) - 2) / (1 - r * r))
                rp = _norm_sf(tstat)
                # MI + 置换
                mi_obs = _mutual_info(xt, yt)
                ge = 0
                for _ in range(m_perm):
                    yp = yt[:]
                    rnd.shuffle(yp)
                    if _mutual_info(xt, yp) >= mi_obs:
                        ge += 1
                mi_p = (ge + 1) / (m_perm + 1)
                name = f"跨位置耦合 {pos[p]}(t)↔{pos[q]}(t-{k})"
                raw.append({"name": name, "stat": round(r, 4), "mi": round(mi_obs, 4),
                            "pearson_p": round(rp, 4), "mi_p": round(mi_p, 4),
                            "rejects": bool(mi_p < 0.05),
                            "interpretation": (
                                f"Pearson r={r:.3f}(p={rp:.3f}), MI={mi_obs:.3f}(置换p={mi_p:.3f})"
                                f" → {'存在跨位置-时滞耦合' if mi_p < 0.05 else '无显著耦合'}")})

    # (2) 高阶马尔可夫 MI 增量：I(d_t; d_{t-1},d_{t-2}) − I(d_t; d_{t-1})
    for p in range(3):
        tgt = [series[t][p] for t in range(2, n)]
        ctx1 = [series[t - 1][p] for t in range(2, n)]
        ctx2 = [(series[t - 1][p], series[t - 2][p]) for t in range(2, n)]
        mi1 = _mi_pair(tgt, ctx1)
        mi2 = _mi_pair2(tgt, ctx2)
        delta = mi2 - mi1
        ge = 0
        for _ in range(m_perm):
            tp = tgt[:]
            rnd.shuffle(tp)
            d2 = _mi_pair2(tp, ctx2)
            d1 = _mi_pair(tp, ctx1)
            if (d2 - d1) >= delta:
                ge += 1
        pval = (ge + 1) / (m_perm + 1)
        raw.append({"name": f"高阶马尔可夫 {pos[p]}(t|t-1,t-2)", "stat": round(delta, 4),
                    "mi1": round(mi1, 4), "mi2": round(mi2, 4), "mi_p": round(pval, 4),
                    "rejects": bool(pval < 0.05),
                    "interpretation": (
                        f"MI增量={delta:.4f}(置换p={pval:.3f}) → "
                        f"{'二阶上下文额外携带信息' if pval < 0.05 else '一阶已足够，无高阶结构'}")})

    # Benjamini-Hochberg FDR 校正（对 mi_p）
    pv = [t["mi_p"] for t in raw]
    idx = sorted(range(len(pv)), key=lambda i: pv[i])
    m = len(pv)
    thresh = {}
    prev = 1.0
    for rank, i in enumerate(idx, 1):
        val = pv[i]
        q = (rank / m) * 0.05
        accept = val <= q and val <= prev
        prev = min(prev, q) if accept else prev
        thresh[i] = accept
    for i, t in enumerate(raw):
        t["fdr_survivor"] = bool(thresh[i])

    survivors = [t["name"] for t in raw if t["fdr_survivor"]]
    n_rej = sum(1 for t in raw if t["rejects"])
    if survivors:
        summary = (f"跨时序耦合电池共 {m} 项检验，{n_rej} 项原始 p<0.05，"
                   f"经 BH-FDR 后 {len(survivors)} 项存活：{survivors}。"
                   "存在可继续深挖的弱信号空间（需在 OOS 盲窗 + 独立样本上复现）。")
    else:
        summary = (f"跨时序耦合电池共 {m} 项检验，{n_rej} 项原始 p<0.05，"
                   "但经 Benjamini-Hochberg FDR 校正后**无一存活**。在交叉位置-时滞耦合与"
                   "高阶马尔可夫维度上未检出可区分于随机的结构；该方向被诚实收窄，但探索不终止。")
    return {
        "n": n, "m_perm": m_perm, "tests": raw,
        "n_rejected_raw": n_rej, "fdr_survivors": survivors,
        "summary": summary,
        "disclaimer": ("本电池仅探测序列内部结构与交叉耦合，不证明/不否认可预测性；"
                       "任何存活联结须经 OOS 盲窗与独立样本复现，且不得包装成盈利策略。"),
    }


def _mi_pair(xs: list[int], ys: list[int]) -> float:
    return _mutual_info(xs, ys)


def _mi_pair2(xs: list[int], pairs: list[tuple[int, int]], bins: int = 10) -> float:
    """I(X; (Y1,Y2))：把二元上下文离散为 100 格。"""
    jc = [[1.0] * (bins * bins) for _ in range(bins)]
    for a, (b1, b2) in zip(xs, pairs):
        jc[a][b1 * bins + b2] += 1.0
    px = [sum(row) for row in jc]
    py = [sum(jc[r][c] for r in range(bins)) for c in range(bins * bins)]
    tot = float(len(xs) + bins * bins)
    mi = 0.0
    for r in range(bins):
        for c in range(bins * bins):
            pxy = jc[r][c] / tot
            mi += pxy * math.log(pxy / ((px[r] / tot) * (py[c] / tot)))
    return mi


def main():
    ap = argparse.ArgumentParser(description="跨时序微妙联结探测电池")
    ap.add_argument("--db", type=Path, default=ROOT / "sd3d_history.sqlite3")
    ap.add_argument("--permutations", type=int, default=400)
    ap.add_argument("--out", type=Path, default=REPORTS / "structure-latest.json")
    a = ap.parse_args()
    rep = run_battery(a.db, a.permutations)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(rep["summary"])
    print(f"Report: {a.out.resolve()}")


if __name__ == "__main__":
    main()
