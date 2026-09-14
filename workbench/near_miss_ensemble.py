"""近失假设集成 / 元学习（"万一多个弱信号凑在一起有效呢" 的诚实探针）.

背景：进化擂台(`evolution_arena`)把 p<0.2 但未过 FDR 的主张作为 `open_hypotheses`（近失）持续追踪，
并回流为下一轮 `cross_seeds`。但单点近失往往是噪声；科学的下一步是问：**多个弱近失假设
集成起来（投票 / 堆叠），是否在 OOS 盲窗上比任一单点更强、且仍胜过均匀随机基线？**

这正是用户要求的"近失集成"。本模块：

  1. 收割近失候选预测器：
       (a) 最新 evolution 报告的 `open_hypotheses`（近失）——基桩族经 `_build_pro_claims` 映射回预测闭包，
           合成型经 `feats` 重建谓词（`_build_filter`）；
       (b) 引擎状态 `near_miss_seeds`（跨运行累积、带 feats）重建；
       (c) 若收割池偏薄，用**确定性 mini-generation** 在**训练窗口内**生成合成候选、保留 p<0.2 者补足——
           选择只用训练窗口，OOS 盲窗严格不参与，从机制上杜绝数据淘金。
  2. 投票 / 堆叠集成：每个候选号统计"通过多少条近失谓词"，按票数降序（同票按联合频率）取 top_k；
      对 min_votes ∈ {1, ⌈m/3⌉, ⌈m/2⌉, m} 各建一个集成器，观察"越严格越有效还是越松越有效"。
  3. 严格时间前向评估：
       训练窗 [train_start, train_end) —— 仅作参考（可能含选择偏差）；
       OOS 盲窗 [train_end, total)     —— **真正的检验**，每期仅用更早数据。
  4. 对照均匀随机基线（top_k/1000 精确命中）：精确二项检验 + Wilson 95% 置信区间；
     对 (成员 + 集成器) 全部右尾 p 做 Benjamini-Hochberg FDR；并用 Fisher/Stouffer
     组合各成员 OOS p 值给"集体方向"。
  5. 诚实结论：若某集成器 OOS 命中率经 FDR 且盈利性盲评仍显著 → 上报弱集体信号；
     否则诚实收窄——但"当前未检出"≠"不可预测"，探索不终止。

宪章兼容：只读权威 DB、时间前向零泄漏、不产投注建议、所有复杂方法对照均匀随机基线。
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WB = Path(__file__).resolve().parent
for _p in (str(ROOT), str(WB)):
    import sys
    if _p not in sys.path:
        sys.path.insert(0, _p)

from predictive_eval import (  # noqa: E402
    load_numbers, binom_two_sided, binom_sf, benjamini_hochberg,
)
from debate_arena import (  # noqa: E402
    ALL_NUMBERS, _joint, _pad, _build_pro_claims, _filter_combine,
)
from evolution_arena import _build_filter, FEAT_POOL  # noqa: E402

REPORTS = ROOT / "reports"
EVOLUTION_REPORT = REPORTS / "evolution-arena-latest.json"
ENGINE_STATE = REPORTS / "evolution-engine-state.json"


# ---------------------------------------------------------------------------
# 统计小工具
# ---------------------------------------------------------------------------
def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _chi2_sf_comb(pvals: list[float]) -> float:
    """Fisher 组合 p 的上尾（chi2 with 2m df），零分布下由 debate_arena.chi2_sf 给出。"""
    from debate_arena import chi2_sf
    if not pvals:
        return 1.0
    fish = -2.0 * sum(math.log(max(p, 1e-300)) for p in pvals)
    return chi2_sf(fish, 2 * len(pvals))


# ---------------------------------------------------------------------------
# 近失预测器收割
# ---------------------------------------------------------------------------
def _stable_seed(feats) -> int:
    return sum(ord(c) for c in ",".join(feats)) % (2 ** 31)


def _harvest_from_report(report: dict, base_map: dict) -> list[tuple[str, object, str]]:
    """返回 [(sig_key, predict_fn, label), ...]。去重由调用方处理。"""
    out = []
    for l in report.get("open_hypotheses", []):
        feats = l.get("feats")
        cid = l.get("claim_id", "")
        if feats:
            filt = _build_filter(list(feats), random.Random(_stable_seed(feats)))
            pred = (lambda f: (lambda train, tk: _filter_combine(train, f, tk)))(filt)
            out.append((("feats", tuple(feats)), pred, f"近失合成·{feats}"))
        else:
            base_id = cid.split("__mut")[0]
            claim = base_map.get(base_id)
            if claim:
                out.append((("base", base_id), claim["predict"], f"近失基桩·{base_id}"))
    return out


def _harvest_from_state(state: dict) -> list[tuple[str, object, str]]:
    out = []
    for seed in state.get("near_miss_seeds", []) or []:
        feats = seed.get("feats")
        if feats:
            filt = _build_filter(list(feats), random.Random(_stable_seed(feats)))
            pred = (lambda f: (lambda train, tk: _filter_combine(train, f, tk)))(filt)
            out.append((("seedfeats", tuple(feats)), pred, f"跨运行种子·{feats}"))
    return out


def _enrich_synthetic(nums, train_start, train_end, top_k, pool_sig, target_min=8,
                      max_gen=240, seed=20260914) -> list[tuple[str, object, str]]:
    """在**训练窗口内**生成合成候选、保留 p<0.2 的近失补足池。OOS 盲窗不参与。"""
    rng = random.Random(seed)
    added = []
    gen = 0
    while len(pool_sig) + len(added) < target_min and gen < max_gen:
        gen += 1
        k = rng.randint(1, 3)
        feats = rng.sample(FEAT_POOL, k=k)
        filt = _build_filter(feats, rng)
        pred = (lambda f: (lambda train, tk: _filter_combine(train, f, tk)))(filt)
        r = _eval_window(pred, nums, train_start, train_end, top_k)
        if r is None:
            continue
        if r["two_sided_p"] is not None and r["two_sided_p"] < 0.2:
            sig = ("synth", tuple(feats), gen)
            added.append((sig, pred, f"合成近失#{gen}·{feats}"))
    return added


# ---------------------------------------------------------------------------
# 严格时间前向评估（本模块自包含，零泄漏）
# ---------------------------------------------------------------------------
def _eval_window(predict_fn, nums: list[tuple[int, str]], start: int, end: int, top_k: int) -> dict | None:
    if end <= start or start < 1:
        return None
    exact = 0
    n = 0
    for i in range(start, end):
        train = [x[1] for x in nums[:i]]
        cands = predict_fn(train, top_k) or []
        if nums[i][1] in cands:
            exact += 1
        n += 1
    if n == 0:
        return None
    p0 = top_k / 1000.0
    return {
        "n": n, "exact_hits": exact, "exact_rate": exact / n,
        "expected_exact_rate": p0,
        "two_sided_p": binom_two_sided(exact, n, p0),
        "exceeds_baseline_p": binom_sf(exact, n, p0),
        "ci95": _wilson(exact, n),
        "verdict": (
            "显著优于随机基线" if (exact > n * p0 and binom_sf(exact, n, p0) < 0.05)
            else ("显著劣于随机基线" if (exact < n * p0 and (1 - binom_sf(exact - 1, n, p0) if exact > 0 else 1.0) < 0.05)
                  else "与随机基线无显著差异")),
    }


# ---------------------------------------------------------------------------
# 集成预测器（投票 / 堆叠）
# ---------------------------------------------------------------------------
def _ensemble_predict(train: list[str], top_k: int, member_predictors: list, min_votes: int) -> list[str]:
    """投票 / 堆叠集成：统计每个候选号被多少条近失成员预测器覆盖，按票数降序取 top_k。

    `member_predictors` 为统一的全预测器接口 `(train, top_k) -> list[str]`：
    合成近失由 `_filter_combine` 包装、基桩近失直接用 `_build_pro_claims` 的 predict。
    每期先一次性算出各成员的候选集合，再对 1000 个候选号计票，避免重复调用。
    """
    joint = _joint(train)
    m = len(member_predictors)
    mv = max(1, min(min_votes, m))
    sets = [set(mp(train, top_k)) for mp in member_predictors]
    scored = []
    for num in ALL_NUMBERS:
        v = sum(1 for s in sets if num in s)
        if v >= mv:
            scored.append((v, joint.get(num, 0), num))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    res = [x[2] for x in scored]
    return _pad(train, joint, res, top_k)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run_ensemble(db: Path, last_n: int = 200, top_k: int = 10, oos_n: int = 60,
                 target_min: int = 8, out: Path | None = None) -> dict:
    nums = load_numbers(db)
    if len(nums) <= last_n + oos_n:
        return {"error": "样本不足", "n": len(nums)}
    total = len(nums)
    train_end = total - oos_n
    train_start = max(1, train_end - last_n)

    # 基桩映射
    base_map = {c["id"]: c for c in _build_pro_claims()}

    # 收割
    pool_sig: dict = {}
    pool: list[tuple[str, object, str]] = []
    harvested_meta = {"report": 0, "state": 0, "synthetic": 0}

    if EVOLUTION_REPORT.exists():
        rep = json.loads(EVOLUTION_REPORT.read_text(encoding="utf-8"))
        for sig, pred, label in _harvest_from_report(rep, base_map):
            if sig not in pool_sig:
                pool_sig[sig] = True
                pool.append((sig, pred, label))
                harvested_meta["report"] += 1

    if ENGINE_STATE.exists():
        st = json.loads(ENGINE_STATE.read_text(encoding="utf-8"))
        for sig, pred, label in _harvest_from_state(st):
            if sig not in pool_sig:
                pool_sig[sig] = True
                pool.append((sig, pred, label))
                harvested_meta["state"] += 1

    # 补足
    if len(pool) < target_min:
        for sig, pred, label in _enrich_synthetic(nums, train_start, train_end, top_k, pool_sig, target_min):
            if sig not in pool_sig:
                pool_sig[sig] = True
                pool.append((sig, pred, label))
                harvested_meta["synthetic"] += 1

    if not pool:
        return {"error": "无可集成的近失候选", "harvested": harvested_meta}

    filters = [p[1] for p in pool]
    m = len(filters)

    # 成员单体评估（训练窗参考 + OOS 盲窗）
    members = []
    for sig, pred, label in pool:
        tr = _eval_window(pred, nums, train_start, train_end, top_k)
        oo = _eval_window(pred, nums, train_end, total, top_k)
        members.append({
            "label": label, "sig": list(sig) if isinstance(sig, tuple) else sig,
            "train": tr, "oos": oo,
        })

    # 集成器评估（min_votes 扫描）
    ensembles = []
    for mv in sorted(set([1, max(1, m // 3), max(1, m // 2), m])):
        pred = (lambda fl, mv=mv: (lambda train, tk: _ensemble_predict(train, tk, fl, mv)))(filters)
        tr = _eval_window(pred, nums, train_start, train_end, top_k)
        oo = _eval_window(pred, nums, train_end, total, top_k)
        ensembles.append({"min_votes": mv, "m": m, "train": tr, "oos": oo})

    # FDR（对成员 + 集成器的 OOS 右尾 p）
    candidates = []
    for mem in members:
        if mem["oos"]:
            candidates.append(("成员:" + mem["label"], mem["oos"]["exceeds_baseline_p"]))
    for ens in ensembles:
        if ens["oos"]:
            candidates.append((f"集成(min_votes={ens['min_votes']})", ens["oos"]["exceeds_baseline_p"]))
    pv = [c[1] for c in candidates]
    rej = benjamini_hochberg(pv, q=0.05) if pv else []
    fdr_results = [{"name": c[0], "oos_exceeds_p": round(c[1], 4), "fdr_survivor": bool(r)}
                   for c, r in zip(candidates, rej)]

    # 集体方向：Fisher / Stouffer 组合各成员 OOS two_sided_p
    member_oos_p = [mem["oos"]["two_sided_p"] for mem in members
                    if mem["oos"] and mem["oos"]["two_sided_p"] is not None]
    fisher_p = _chi2_sf_comb(member_oos_p)
    # Stouffer Z
    zs = []
    for mem in members:
        o = mem["oos"]
        if o and o["n"]:
            zs.append((o["exact_hits"] - o["n"] * o["expected_exact_rate"])
                      / math.sqrt(max(1e-9, o["n"] * o["expected_exact_rate"] * (1 - o["expected_exact_rate"]))))
    stouffer_z = (sum(zs) / math.sqrt(len(zs))) if zs else 0.0
    from math import erf
    stouffer_p = 0.5 * (1 - erf(abs(stouffer_z) / math.sqrt(2)))

    # 最佳集成 OOS
    best_ens = max((e for e in ensembles if e["oos"]), key=lambda e: e["oos"]["exact_rate"], default=None)
    best_oos_rate = best_ens["oos"]["exact_rate"] if best_ens else None
    best_beats = (best_ens and best_ens["oos"]["exceeds_baseline_p"] < 0.05
                  and best_oos_rate > best_ens["oos"]["expected_exact_rate"])
    fdr_surv_any = any(r["fdr_survivor"] for r in fdr_results)

    # 诚实结论
    if best_beats and fdr_surv_any:
        winner = "weak_collective_signal"
        conclusion = (
            "近失假设经投票/堆叠集成后，在 OOS 盲窗上命中率显著且经 FDR 仍超越均匀随机基线；"
            "存在可继续深挖的弱集体信号。但须扣除成本后盲评复核，且不构成投注建议。")
    else:
        winner = "random"
        conclusion = (
            "近失集成（投票/堆叠）在 OOS 盲窗上命中率与均匀随机基线无显著差异，"
            "FDR 校正后无集成器存活；单点近失的'集体投票'未浮现可检测信号——该方向被诚实收窄。"
            "但'当前未检出'≠'不可预测'：混沌系统（天气/湍流）同样难以精确预测却始终可被建模逼近；"
            "本引擎以开放心态持续追踪弱信号，绝不把'不可预测'预设为终局假设。探索不终止。")

    report = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "config": {"last_n": last_n, "top_k": top_k, "oos_n": oos_n,
                   "target_min_members": target_min, "total_draws": total,
                   "train_window": [train_start, train_end], "oos_window": [train_end, total]},
        "harvested": harvested_meta, "pool_size": m,
        "members": members,
        "ensembles": ensembles,
        "fdr_results": fdr_results,
        "portfolio": {
            "n_members_with_oos": len(member_oos_p),
            "fisher_p": round(fisher_p, 5), "stouffer_z": round(stouffer_z, 4),
            "stouffer_p": round(stouffer_p, 5),
        },
        "best_ensemble_oos": {
            "min_votes": best_ens["min_votes"] if best_ens else None,
            "exact_rate": round(best_oos_rate, 5) if best_oos_rate is not None else None,
            "beats_baseline": bool(best_beats),
        },
        "final_verdict": {
            "winner": winner,
            "winner_label": {
                "weak_collective_signal": "近失集成浮现弱集体信号，需盲评复核",
                "random": "当前未检出可区分信号 · 但探索持续开放（不预设不可预测）",
            }[winner],
            "conclusion": conclusion,
            "fdr_note": (
                f"对 {len(candidates)} 个(成员+集成器)的 OOS 右尾 p 做 BH-FDR 校正后，"
                f"{sum(1 for r in fdr_results if r['fdr_survivor'])} 个存活。"),
        },
        "disclaimer": (
            "近失集成是假设检验与元学习演示，不构成任何投注建议。即使集成器统计显著，"
            "也须扣除成本后仍盈利方可实用（统计显著 ≠ 实战可盈利）。统计未检出 ≠ 证明纯随机，"
            "仅表示'当前证据下无可检测的集体可预测信号'。"),
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser(description="近失假设集成 / 元学习")
    ap.add_argument("--db", type=Path, default=ROOT / "sd3d_history.sqlite3")
    ap.add_argument("--last-n", type=int, default=200)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--oos-n", type=int, default=60)
    ap.add_argument("--target-min", type=int, default=8)
    ap.add_argument("--out", type=Path, default=REPORTS / "near-miss-ensemble-latest.json")
    a = ap.parse_args()
    rep = run_ensemble(a.db, a.last_n, a.top_k, a.oos_n, a.target_min, a.out)
    if rep.get("error"):
        print("ERROR:", rep["error"])
        return
    fv = rep["final_verdict"]
    print(f"收割: 报告{rep['harvested']['report']} 状态{rep['harvested']['state']} 合成{rep['harvested']['synthetic']} → 池大小 {rep['pool_size']}")
    print(f"Fisher 组合 p={rep['portfolio']['fisher_p']} · Stouffer Z={rep['portfolio']['stouffer_z']}")
    print(f"最佳集成 OOS 命中率={rep['best_ensemble_oos']['exact_rate']} · 胜基线={rep['best_ensemble_oos']['beats_baseline']}")
    print(f"裁决: {fv['winner_label']}")
    print(f"结论: {fv['conclusion'][:120]}...")
    print(f"报告: {a.out.resolve()}")


if __name__ == "__main__":
    main()
