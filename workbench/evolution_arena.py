"""自进化辩论擂台（Evolution Arena）— 激励 + 自进化 + 决策方向科学评价.

在「双阵营辩论擂台」基础上扩展为闭环元系统：

  自进化元循环  →  独立审计(FDR/安慰剂/复现)  →  决策方向科学评价  →  激励账本奖惩  →  反馈下一代生成

三大支柱：
  1. 激励账本 (IncentiveLedger)：AP/RP 积分 + 独立 Reputation + 徽章，奖惩锚定审计结果。
  2. AI 自进化元循环：生成(突变/组合 + 随机问题生成器 + 综合特征交叉) → 审计 → 缺口闭环
     → 谱系(parent→child) → 下一代；OOS 盲窗 + 全局 FDR 递增惩罚 防过拟合/数据淘金。
  3. 决策方向科学评价：Fisher/Stouffer 组合 p + 组合贝叶斯因子 + 方向标量
     score=tanh(Z)∈(-1,+1) + CI(零分布置换校准) + TOST 等价措辞。

宪章合规（内建）：
  * 文章 1 — 把辩论当作随机性检验，从不假定可预测。
  * 文章 2 — 对权威 DB 只读。
  * 文章 10 — 每个主张都与均匀随机基线做精确二项检验；只有经 FDR 且盈利才"胜"；
    方向得分≈0/负 一律输出"未检出可预测信号"，绝不包装成盈利策略。
  * 时间前向、零泄漏：每个目标期仅用更早数据预测；OOS 盲窗训练严格限定在其之前。
"""

from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WB = Path(__file__).resolve().parent
for _p in (str(ROOT), str(WB)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from predictive_eval import (  # noqa: E402
    binom_sf,
    binom_two_sided,
    load_numbers,
    benjamini_hochberg,
)
from debate_arena import (  # noqa: E402
    run_arsenal,
    _build_pro_claims,
    _cohens_h,
    _bayes_factor,
    _dist_recent,
    _filter_combine,
    _sum,
    chi2_sf,
)
from incentive_ledger import IncentiveLedger  # noqa: E402

REPORTS = ROOT / "reports"

ENGINE_STATE_PATH = REPORTS / "evolution-engine-state.json"


def _load_engine_state(path: Path) -> dict:
    """读取跨运行引擎状态（账本 + 近失种子 + 运行计数）。缺失/损坏时返回空状态。"""
    if not path.exists():
        return {"ledger": None, "near_miss_seeds": [], "runs": 0,
                "last_generated_at": None, "last_score": None, "last_winner": None}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {"ledger": None, "near_miss_seeds": [], "runs": 0,
                "last_generated_at": None, "last_score": None, "last_winner": None}


def _save_engine_state(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

FEAT_POOL = ["digit", "parity", "prime", "sum", "sum_tail", "span", "trend",
             "pos_pair", "sum_digit", "span_parity"]
PRIMES = {2, 3, 5, 7}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _merit_w(cohens_h: float, bayes_factor: float) -> float:
    try:
        bf = bayes_factor if (bayes_factor and bayes_factor > 0) else 1e-300
        return _clamp(abs(cohens_h) * 2.0 + math.log(bf), 0.0, 1.0)
    except Exception:
        return 0.0


# ===========================================================================
# 主张生成器（自进化元循环的生成侧）
# ===========================================================================
def _build_filter(features: list[str], rng: random.Random):
    """由特征原语集合合成一个谓词过滤器（用于随机/综合问题生成器）。"""
    conds = []
    if "parity" in features:
        keep = rng.choice([0, 1])
        conds.append(lambda n, keep=keep: (
            int(n[0]) % 2 == keep and int(n[1]) % 2 == keep and int(n[2]) % 2 == keep))
    if "prime" in features:
        keep = rng.choice([True, False])
        conds.append(lambda n, keep=keep: (
            ((int(n[0]) in PRIMES) == keep) and ((int(n[1]) in PRIMES) == keep)
            and ((int(n[2]) in PRIMES) == keep)))
    if "sum" in features:
        s = rng.randint(0, 27)
        conds.append(lambda n, s=s: _sum(n) == s)
    if "sum_tail" in features:
        st = rng.randint(0, 9)
        conds.append(lambda n, st=st: _sum(n) % 10 == st)
    if "span" in features:
        sp = rng.randint(0, 9)
        conds.append(lambda n, sp=sp: int(max(n)) - int(min(n)) == sp)
    if "trend" in features:
        step = rng.choice([-1, 0, 1])
        conds.append(lambda n, step=step: (int(n[2]) - int(n[1])) == step)
    if "digit" in features:
        d = str(rng.randint(0, 9))
        pos = rng.randint(0, 2)
        conds.append(lambda n, d=d, pos=pos: n[pos] == d)
    # —— 关系型/交互型原语：捕捉"事物之间的微妙联结"（而非单变量谓词）——
    if "pos_pair" in features:
        # 两位之间的联结：同奇偶 / 相等 / 相差1（位间结构）
        mode = rng.choice(["same_parity", "equal", "diff_one"])
        a, b = rng.sample([0, 1, 2], 2)
        if mode == "same_parity":
            conds.append(lambda n, a=a, b=b: (int(n[a]) % 2) == (int(n[b]) % 2))
        elif mode == "equal":
            conds.append(lambda n, a=a, b=b: n[a] == n[b])
        else:
            conds.append(lambda n, a=a, b=b: abs(int(n[a]) - int(n[b])) == 1)
    if "sum_digit" in features:
        # 和尾 与 某一位数字耦合（和值—位值的微妙联结）
        p = rng.randint(0, 2)
        conds.append(lambda n, p=p: (_sum(n) % 10) == int(n[p]))
    if "span_parity" in features:
        # 跨度奇偶 与 某一位奇偶耦合（跨度—单值的微妙联结）
        p = rng.randint(0, 2)
        conds.append(lambda n, p=p: ((int(max(n)) - int(min(n))) % 2) == (int(n[p]) % 2))
    if not conds:
        conds.append(lambda n: True)

    def filt(n: str) -> bool:
        return all(c(n) for c in conds)

    return filt


def _generate_candidates(base_claims: list[dict], prior_near_miss: list[dict],
                         gen: int, rng: random.Random, new_per_gen: int, top_k: int,
                         cross_seeds: list[dict] | None = None,
                         run: int = 0) -> list[dict]:
    """生成下一代候选主张：突变(base/近失) + 随机问题生成器 + 综合特征交叉。

    `run` 为当前引擎运行序号，嵌入所有「非基桩」候选 id，确保跨运行 id 全局唯一，
    避免不同次运行生成的（特征不同的）主张撞同一 id 而污染账本归因。
    """
    new: list[dict] = []
    pool = list(base_claims) + list(prior_near_miss)
    rng.shuffle(pool)
    # (a) mutate：对 base/近失 主张扰动回看窗口（复用其 predict，配新分布）
    for c in pool:
        if len(new) >= new_per_gen // 2:
            break
        w = rng.choice([50, 100, 200, 400])
        new.append({
            "id": f"{c['id']}__mut{run}_{gen}_{w}",
            "name": f"{c['name']}·突变(窗{w})",
            "family": c["family"] + "(突变)",
            "belief": c["belief"] + f"；突变窗口={w}",
            "predict": c["predict"],
            "distribution": _dist_recent(w),
            "origin": "mutate", "parent_ids": [c["id"]], "generation": gen,
        })
    # (b)+(c) random / comprehensive：合成谓词（k>=3 视为综合特征交叉）
    while len(new) < new_per_gen:
        k = rng.randint(1, 3)
        feats = rng.sample(FEAT_POOL, k=k)
        fid = f"synth_{run}_{gen}_{len(new)}"
        filt = _build_filter(feats, rng)
        win = rng.choice([50, 100, 200])
        new.append({
            "id": fid,
            "name": f"合成假说#{gen}.{len(new)}",
            "family": "synthetic",
            "belief": "随机问题生成器合成假设：" + ",".join(feats),
            "predict": (lambda f: (lambda train, tk: _filter_combine(train, f, tk)))(filt),
            "distribution": _dist_recent(win),
            "origin": ("comprehensive" if k >= 3 else "random"),
            "parent_ids": [], "generation": gen, "feats": feats,
        })
    # cross-run seeds: replay prior near-miss feature combos as fresh candidates
    # (heuristic: re-derive the filter from the persisted feature spec; the exact
    # predict closure is not serializable, so we regenerate it with a fresh window)
    for cs in (cross_seeds or [])[:3]:
        if len(new) >= new_per_gen:
            break
        feats = cs.get("feats")
        if not feats:
            continue
        fid = f"xseed_{run}_{gen}_{len(new)}"
        filt = _build_filter(feats, rng)
        win = rng.choice([50, 100, 200])
        new.append({
            "id": fid,
            "name": f"跨运行种子#{gen}.{len(new)}",
            "family": "synthetic",
            "belief": "跨运行复用近失特征组合：" + ",".join(feats),
            "predict": (lambda f: (lambda train, tk: _filter_combine(train, f, tk)))(filt),
            "distribution": _dist_recent(win),
            "origin": ("comprehensive" if len(feats) >= 3 else "random"),
            "parent_ids": [], "generation": gen, "feats": feats,
        })
    return new[:new_per_gen]


# ===========================================================================
# 评估（严格窗口，时间前向，零泄漏）
# ===========================================================================
def _evaluate_window(claim: dict, nums: list[tuple[int, str]], start: int, end: int, top_k: int) -> dict | None:
    """在 [start, end) 目标期上做严格扩展窗口评估；每个目标仅用更早数据训练。"""
    if end <= start or start < 1:
        return None
    exact = 0
    n = 0
    pred = claim["predict"]
    for i in range(start, end):
        train = [x[1] for x in nums[:i]]
        cands = pred(train, top_k) or []
        if nums[i][1] in cands:
            exact += 1
        n += 1
    if n == 0:
        return None
    p0 = top_k / 1000.0
    two = binom_two_sided(exact, n, p0)
    exceeds = binom_sf(exact, n, p0)
    worse = 1.0 - binom_sf(exact - 1, n, p0) if exact > 0 else 1.0
    if exact > n * p0 and exceeds < 0.05:
        verdict = "显著优于随机基线"
    elif exact < n * p0 and worse < 0.05:
        verdict = "显著劣于随机基线"
    else:
        verdict = "与随机基线无显著差异"
    return {
        "n": n, "exact_hits": exact, "exact_rate": exact / n,
        "expected_exact_rate": p0, "two_sided_p": two, "exceeds_baseline_p": exceeds,
        "worse_than_baseline_p": worse, "verdict": verdict,
    }


def _placebo_window(claim: dict, nums: list[tuple[int, str]], start: int, end: int,
                    top_k: int, seed: int) -> float:
    """安慰剂/标签置换稳健性：打乱 [start,end) 的目标号码后重评，返回 exceeds_p。"""
    work = list(nums)
    tail = [work[i][1] for i in range(start, end)]
    rnd = random.Random(seed)
    rnd.shuffle(tail)
    for idx, i in enumerate(range(start, end)):
        work[i] = (work[i][0], tail[idx])
    exact = 0
    n = 0
    for i in range(start, end):
        train = [x[1] for x in work[:i]]
        cands = claim["predict"](train, top_k) or []
        if work[i][1] in cands:
            exact += 1
        n += 1
    if n == 0:
        return 1.0
    return binom_sf(exact, n, top_k / 1000.0)


def _split_half_window(claim: dict, nums: list[tuple[int, str]], start: int, end: int, top_k: int) -> bool:
    mid = (start + end) // 2

    def _rate(a: int, b: int) -> float:
        if b <= a:
            return 0.0
        exact = 0
        n = 0
        for i in range(a, b):
            train = [x[1] for x in nums[:i]]
            c = claim["predict"](train, top_k) or []
            if nums[i][1] in c:
                exact += 1
            n += 1
        return (exact / n - top_k / 1000.0) if n else 0.0

    e_fh = _rate(start, mid)
    e_sh = _rate(mid, end)
    return (e_fh >= 0) == (e_sh >= 0)


def collect_evidence(claim: dict, nums: list[tuple[int, str]], start: int, end: int,
                    top_k: int, alpha: float) -> dict | None:
    r = _evaluate_window(claim, nums, start, end, top_k)
    if r is None:
        return None
    p0 = r["expected_exact_rate"]
    p1 = r["exact_rate"]
    h = _cohens_h(p1, p0)
    bf = _bayes_factor(r["exact_hits"], r["n"], p0)
    rec = {
        "claim": claim["id"], "name": claim["name"], "family": claim["family"],
        "belief": claim["belief"], "origin": claim.get("origin", ""),
        "parent_ids": claim.get("parent_ids", []), "generation": claim.get("generation", 0),
        "n": r["n"], "exact_hits": r["exact_hits"], "exact_rate": p1, "expected_exact_rate": p0,
        "two_sided_p": r["two_sided_p"], "exceeds_baseline_p": r["exceeds_baseline_p"],
        "verdict": r["verdict"], "effect_size_h": h, "bayes_factor": bf,
        "placebo_exceed_p": None, "placebo_robust": None, "split_half_consistent": None,
        "fdr_survivor": False, "rejected": True, "reject_reason": "",
        "merit_w": _merit_w(h, bf),
    }
    if r["verdict"] == "显著优于随机基线":
        rec["rejected"] = False
        rec["reject_reason"] = "原始检验显著优于基线（待 FDR 与额外闸门复核）"
    else:
        rec["reject_reason"] = "命中率与均匀随机基线无显著差异（原始检验未通过）"
    if rec["exceeds_baseline_p"] is not None and rec["exceeds_baseline_p"] < alpha:
        rec["placebo_exceed_p"] = _placebo_window(claim, nums, start, end, top_k, 20260911)
        rec["placebo_robust"] = rec["placebo_exceed_p"] >= alpha
        rec["split_half_consistent"] = _split_half_window(claim, nums, start, end, top_k)
    return rec


def _fdr_gate_global(evidences: list[dict], q_eff: float) -> None:
    """全局 FDR 校正（q_eff 已含递增惩罚）。"""
    pvals = [e["exceeds_baseline_p"] for e in evidences if e["exceeds_baseline_p"] is not None]
    idx = [i for i, e in enumerate(evidences) if e["exceeds_baseline_p"] is not None]
    if not pvals:
        return
    rej = benjamini_hochberg(pvals, q=q_eff)
    for j, i in enumerate(idx):
        e = evidences[i]
        if rej[j]:
            e["fdr_survivor"] = True
            e["rejected"] = False
            reason = "通过 FDR 校正，仍显著优于基线"
            if e["placebo_exceed_p"] is not None:
                reason += "；" + ("安慰剂稳健" if e["placebo_robust"] else "安慰剂同样显著(伪信号)")
            if e["split_half_consistent"] is not None:
                reason += "；" + ("可复现" if e["split_half_consistent"] else "不可复现")
            e["reject_reason"] = reason
        else:
            e["rejected"] = True
            e["reject_reason"] = "原始显著但经 Benjamini-Hochberg FDR 校正后被否（多重比较伪阳性）"


# ===========================================================================
# 决策方向科学评价（组合证据 → 单一方向标量 + 置信）
# ===========================================================================
def _directional_score(evidences: list[dict]) -> dict:
    """把全部证据压成单一决策方向标量 score=tanh(Z)∈(-1,+1) 与置信区间。

    关键区分：H⁺(可预测) vs H₀(纯随机)。H₀ 不能被证明为真，只用 TOST 等价检验
    判断'效应小到无实践意义'；结论措辞必须是'未检出可预测信号'，绝不写成'已证明纯随机'。
    """
    zs = []
    for e in evidences:
        n = e.get("n")
        k = e.get("exact_hits")
        p0 = e.get("expected_exact_rate")
        if not n or p0 in (None, 0):
            continue
        z = (k - n * p0) / math.sqrt(max(1e-9, n * p0 * (1 - p0)))
        zs.append(z)
    m = len(zs)
    if m == 0:
        return {
            "score": 0.0, "score_ci": [0.0, 0.0], "confidence_predictable": 0.5,
            "confidence_random_equiv": 0.5, "fisher_p": 1.0, "stouffer_z": 0.0,
            "bayes_factor_portfolio": 1.0,
            "null_calibration": {"n_sim": 0, "score_null_mean": 0.0, "score_null_p95": 0.0,
                                 "score_null_p975": 0.0, "exceeds_null": False},
            "conclusion": "no_evidence_of_predictability", "max_effect_h": 0.0,
        }
    Z = sum(zs) / math.sqrt(m)            # Stouffer Z, ~N(0,1) under H0
    score = math.tanh(Z)
    lo, hi = Z - 1.96, Z + 1.96
    ci = [math.tanh(lo), math.tanh(hi)]
    # Fisher 组合 p（非方向性，作为稳健性补充）
    pvals = [e["two_sided_p"] for e in evidences if e.get("two_sided_p") is not None]
    if pvals:
        fish = -2 * sum(math.log(max(p, 1e-300)) for p in pvals)
        fisher_p = chi2_sf(fish, 2 * len(pvals))
    else:
        fisher_p = 1.0
    # 组合贝叶斯因子（按 merit_w 加权）
    logbf_num = 0.0
    wsum = 0.0
    max_h = 0.0
    for e in evidences:
        bf = e.get("bayes_factor")
        w = e.get("merit_w", 0.5) or 0.5
        if bf and bf > 0:
            logbf_num += w * math.log(bf)
            wsum += w
        h = abs(e.get("effect_size_h") or 0)
        if h > max_h:
            max_h = h
    bf_port = math.exp(logbf_num / wsum) if wsum > 0 else 1.0
    conf_pred = bf_port / (1.0 + bf_port)
    # 零分布校准（参数化：m 个独立 N(0,1) 叠加，匹配 H0 行为）
    N_SIM = 2000
    sims = [sum(random.gauss(0, 1) for _ in range(m)) / math.sqrt(m) for _ in range(N_SIM)]
    sim_scores = sorted(math.tanh(s) for s in sims)
    p95 = sim_scores[int(0.95 * len(sim_scores))]
    p975 = sim_scores[int(0.975 * len(sim_scores))]
    exceeds = score > p975
    # TOST 等价：最大效应量是否小到无实践意义
    delta = 0.1
    conf_random_equiv = 0.95 if max_h < delta else max(0.0, 1.0 - (max_h - delta) / 0.3)
    if fisher_p > 0.05 and conf_pred < 0.6 and not exceeds:
        conclusion = "no_evidence_of_predictability"
    elif conf_pred >= 0.6:
        conclusion = "weak_signal"
    else:
        conclusion = "inconclusive"
    return {
        "score": round(score, 4), "score_ci": [round(ci[0], 4), round(ci[1], 4)],
        "confidence_predictable": round(conf_pred, 4),
        "confidence_random_equiv": round(conf_random_equiv, 4),
        "fisher_p": round(fisher_p, 5), "stouffer_z": round(Z, 4),
        "bayes_factor_portfolio": round(bf_port, 4),
        "null_calibration": {"n_sim": N_SIM, "score_null_mean": round(float(statistics_mean(sim_scores)), 4),
                              "score_null_p95": round(p95, 4), "score_null_p975": round(p975, 4),
                              "exceeds_null": bool(exceeds)},
        "conclusion": conclusion, "max_effect_h": round(max_h, 4),
    }


def statistics_mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


# ===========================================================================
# 自进化元循环引擎
# ===========================================================================
class EvolutionArena:
    def __init__(self, db: Path, last_n: int = 200, top_k: int = 10, alpha: float = 0.1,
                 fdr_q: float = 0.05, max_gens: int = 3, prize: float = 1040.0,
                 cost: float = 2.0, oos_n: int = 60, seed: int = 20260911,
                 new_per_gen: int = 8, m0: int = 15, prev_state: dict | None = None):
        self.db = db
        self.last_n = last_n
        self.top_k = top_k
        self.alpha = alpha
        self.fdr_q = fdr_q
        self.max_gens = max_gens
        self.prize = prize
        self.cost = cost
        self.oos_n = oos_n
        self.seed = seed
        self.new_per_gen = new_per_gen
        self.m0 = m0
        self.prev_state = prev_state or {}
        self.rng = random.Random(seed)
        self.nums = load_numbers(db)
        self.total = len(self.nums)
        # 训练评估窗口：严格排除 OOS 盲窗（不回看 OOS 数据）
        self.train_end = max(2, self.total - oos_n)
        self.train_start = max(1, self.train_end - last_n)
        # 跨运行累积：账本与近失种子从上一运行继承
        self.ledger = (IncentiveLedger.from_dict(self.prev_state["ledger"])
                       if self.prev_state.get("ledger") else IncentiveLedger())
        self.prev_near_miss_seeds = self.prev_state.get("near_miss_seeds", []) or []
        self.engine_runs = (self.prev_state.get("runs", 0) or 0) + 1
        self.prev_score = self.prev_state.get("last_score")
        self.prev_winner = self.prev_state.get("last_winner")
        self.lineage: dict[str, dict] = {}
        self.claim_registry: dict[str, dict] = {}
        self.search_ever_open = False   # 探索永不主动关闭（反"躺平"姿态标志）
        self.base_claims = _build_pro_claims()
        for c in self.base_claims:
            self.claim_registry[c["id"]] = c

    def _register(self, c: dict) -> None:
        self.claim_registry[c["id"]] = c

    def _claim_by_id(self, cid: str):
        return self.claim_registry.get(cid)

    def _apply_ledger(self, c: dict, e: dict) -> None:
        cid = c["id"]
        # 跨运行防双计：若该主张在上一次运行已定案，本次不再重复计分
        if self.ledger.claims.get(cid, {}).get("status") not in (None, "pending"):
            return
        if e["fdr_survivor"]:
            self.ledger.survive(cid, e["merit_w"])
            self.ledger.wrongful_reject(cid)   # 反方挑战了但最终存活 -> 反方误驳
        else:
            # 正方诚实撤回（明显劣于基线者主动认错） vs 反方正确驳回
            if e["verdict"] == "显著劣于随机基线":
                self.ledger.retract(cid)
            else:
                dec = _clamp((0.05 - (e["two_sided_p"] or 0.5)) / 0.05, 0.0, 1.0)
                self.ledger.reject(cid, dec)

    def _lineage_record(self, c: dict, e: dict) -> dict:
        return {
            "claim_id": c["id"], "generation": c.get("generation", 0),
            "origin": c.get("origin", ""), "family": c.get("family", ""),
            "parent_ids": c.get("parent_ids", []), "feats": c.get("feats"),
            "fitness": {
                "n": e["n"],
                "exact_rate": round(e["exact_rate"], 5),
                "expected_exact_rate": round(e["expected_exact_rate"], 5),
                "two_sided_p": round(e["two_sided_p"], 4) if e["two_sided_p"] is not None else None,
                "effect_size_h": round(e["effect_size_h"], 4),
                "bayes_factor": round(e["bayes_factor"], 3),
                "fdr_survivor": e["fdr_survivor"],
                "placebo_robust": e["placebo_robust"],
                "split_half_consistent": e["split_half_consistent"],
            },
            "status": ("survived" if e["fdr_survivor"]
                       else ("near_miss" if (e["two_sided_p"] or 1) < 0.2 else "rejected")),
            "reject_reason": e["reject_reason"],
        }

    def _oos_check(self, survivors_ids: set[str]) -> dict:
        if not survivors_ids:
            return {"survivors": [], "note": "无存活主张，无需盲评"}
        start = max(1, self.total - self.oos_n)
        end = self.total
        results = []
        for cid in survivors_ids:
            c = self._claim_by_id(cid)
            if c is None:
                continue
            r = _evaluate_window(c, self.nums, start, end, self.top_k)
            if r is None:
                continue
            results.append({
                "claim": cid, "name": c["name"], "n": r["n"],
                "exact_rate": round(r["exact_rate"], 5),
                "oos_exceeds_p": round(r["exceeds_baseline_p"], 4),
                "oos_verdict": r["verdict"],
            })
        return {"survivors": results,
                "note": f"对 {len(results)} 个 FDR 存活主张做末 {self.oos_n} 期盲评（训练严格限定在 OOS 窗口之前）"}

    def _final_verdict(self, directional: dict, oos: dict, survivors_ids: set[str]):
        score = directional["score"]
        ci = directional["score_ci"]
        oos_pass = [r for r in oos.get("survivors", [])
                    if r["oos_exceeds_p"] is not None and r["oos_exceeds_p"] < 0.05]
        profit = None
        if oos_pass:
            best = max(oos_pass, key=lambda r: r["exact_rate"])
            profit = best["exact_rate"] * self.prize - self.top_k * self.cost
        if directional["confidence_predictable"] >= 0.6 and oos_pass and (profit or 0) > 0:
            return "weak_signal", (
                "存在经 FDR 校正与盲评双重确认的可预测信号；但样本仍有限，建议扩充数据后盲评复核，"
                "暂不下'可预测'定论。")
        if score >= 0 and ci[0] > 0.05:
            return "weak_signal", (
                "方向得分置信区间整体为正，提示存在微弱可预测成分，但盈利性未经盲评证实，"
                "不构成投注建议。")
        # 「当前未检出」≠「已证伪 / 探索终止」：以开放的科学姿态陈述证据，而非关闭研究。
        return "random", (
            "当前样本与特征空间下，所有主张经精确二项检验 + Benjamini-Hochberg FDR"
            "（含全局递增惩罚）后无一稳定、显著超越均匀随机基线；决策方向得分≈0 且落在零分布带内，"
            "即'当前证据不足以支持可预测信号'。"
            "但这**不是**'开奖为纯随机、探索终止'的结论——混沌系统（如天气、湍流）同样难以精确预测，"
            "却始终可被建模、逼近与改进。本引擎以开放心态持续追踪弱信号与微妙联结，每次运行推进随机种子并回流近失假设，"
            "绝不把'不可预测'预设为终局假设；只要样本、特征空间或视角尚未穷尽，探索就不关闭。")

    def run(self) -> dict:
        all_evidence: list[dict] = []
        generations: list[dict] = []
        survivors_ids: set[str] = set()
        prior_near_miss: list[dict] = []
        m_tested = 0
        # 搜索状态恒为"开放"：本引擎不以"未检出信号"为理由关闭探索
        search_status = "open"

        for gen in range(self.max_gens):
            if gen == 0:
                candidates = self.base_claims
            else:
                candidates = _generate_candidates(
                    self.base_claims, prior_near_miss, gen, self.rng,
                    self.new_per_gen, self.top_k,
                    cross_seeds=self.prev_near_miss_seeds,
                    run=self.engine_runs)
            for c in candidates:
                self._register(c)
                self.ledger.submit(c["id"], c.get("origin", ""))

            evs = [collect_evidence(c, self.nums, self.train_start, self.train_end,
                                   self.top_k, self.alpha) for c in candidates]
            evs = [e for e in evs if e is not None]
            m_tested += len(evs)

            # 全局 FDR 递增惩罚：生成越多假设，阈值越严（防数据淘金）
            q_eff = self.fdr_q * (self.m0 / max(self.m0, m_tested))
            _fdr_gate_global(evs, q_eff)

            ev_by_id = {e["claim"]: e for e in evs}
            near: list[dict] = []
            for c in candidates:
                e = ev_by_id.get(c["id"])
                if e is None:
                    continue
                self._apply_ledger(c, e)
                self.lineage[c["id"]] = self._lineage_record(c, e)
                if not e["fdr_survivor"] and (e["two_sided_p"] or 1) < 0.2:
                    near.append(c)
                if e["fdr_survivor"]:
                    survivors_ids.add(c["id"])

            all_evidence.extend(evs)
            ds = _directional_score(evs)
            gen_surv = [e for e in evs if e["fdr_survivor"]]
            generations.append({
                "generation": gen, "n_claims": len(candidates),
                "n_survivors": len(gen_surv), "score": ds["score"],
                "score_ci": ds["score_ci"], "fisher_p": ds["fisher_p"],
            })

            # 开放探索姿态（反"躺平"）：绝不因"未检出信号"而终止搜索。
            # 连续两代 0 存活且方向得分≈0 仅记为"当前窗口暂无强信号"，不 break；
            # 搜索在达到 max_gens 硬上限前永不主动关闭。跨运行还会推进随机种子 +
            # 回流上一轮近失特征种子，使"没有立刻找到"变成"下一轮换角度继续找"。
            if (gen >= 2 and generations[-1]["n_survivors"] == 0
                    and generations[-2]["n_survivors"] == 0
                    and abs(generations[-1]["score"]) < 0.05):
                self.search_ever_open = True
            prior_near_miss = near

        oos = self._oos_check(survivors_ids)
        directional = _directional_score(all_evidence)
        arsenal = run_arsenal(self.db)
        winner, conclusion = self._final_verdict(directional, oos, survivors_ids)

        profit_per_bet = None
        if oos.get("survivors"):
            best = max(oos["survivors"], key=lambda r: r["exact_rate"])
            profit_per_bet = best["exact_rate"] * self.prize - self.top_k * self.cost

        fdr_note = (
            f"逐代累计测试 {m_tested} 个主张（含突变/合成生成物），经 Benjamini-Hochberg FDR"
            f"（含全局递增惩罚 q_eff）校正后，{len(survivors_ids)} 个稳定、显著超越均匀随机基线。"
        )
        disclaimer = (
            "本进化擂台为假设检验与激励模拟演示，不构成任何投注建议。福彩3D 开奖为受监管随机过程；"
            "即使个别策略统计显著，也须扣除成本后仍盈利方可实用（统计显著 ≠ 实战可盈利）。"
            "统计未检出 ≠ 证明纯随机，仅表示'当前证据下无可检测的可预测信号'。"
            "本项目的姿态：不以'无法预测'开启躺平——像预报天气那样，持续建模、追踪弱信号与微妙联结，"
            "把'不可预测'当作待检验的开放假设，而非探索的终点。")

        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "config": {
                "last_n": self.last_n, "top_k": self.top_k, "alpha": self.alpha,
                "fdr_q": self.fdr_q, "max_gens": self.max_gens, "oos_n": self.oos_n,
                "prize": self.prize, "cost_per_number": self.cost,
                "new_per_gen": self.new_per_gen, "m0": self.m0, "seed": self.seed,
            },
            "ledger": self.ledger.to_dict(),
            "arsenal": arsenal,
            "generations": generations,
            "search_status": search_status,
            "lineage": list(self.lineage.values()),
            # 开放假设：把"近失"(p<0.2 但未过 FDR)的主张框定为仍在探索的开放线索，
            # 而非"失败"。它们会作为近失种子回流到下一轮 cross_seeds 继续检验。
            "open_hypotheses": [
                l for l in self.lineage.values() if l.get("status") == "near_miss"
            ],
            "evidence": all_evidence,
            "directional": directional,
            "oos": oos,
            "engine_state": {
                "runs": self.engine_runs,
                "prev_score": self.prev_score,
                "prev_winner": self.prev_winner,
                "near_miss_seeds_carried": len(self.prev_near_miss_seeds),
                "near_miss_seeds_collected": len([
                    l for l in self.lineage.values()
                    if l.get("status") == "near_miss" and l.get("feats")
                ]),
            },
            "final_verdict": {
                "winner": winner,
                "winner_label": {
                    "random": "当前未检出可区分信号 · 但探索持续开放（不预设不可预测）",
                    "weak_signal": "存在微弱可预测信号，需进一步盲评验证",
                    "inconclusive": "证据不确定，继续探索",
                }[winner],
                "profit_per_bet": (round(profit_per_bet, 4) if profit_per_bet is not None else None),
                "best_survivor": (max(oos["survivors"], key=lambda r: r["exact_rate"])["claim"]
                                  if oos.get("survivors") else None),
                "conclusion": conclusion,
                "fdr_note": fdr_note,
                "disclaimer": disclaimer,
            },
        }
        return report


def run_evolution(db: Path, last_n: int = 200, top_k: int = 10, alpha: float = 0.1,
                  fdr_q: float = 0.05, max_gens: int = 3, prize: float = 1040.0,
                  cost: float = 2.0, oos_n: int = 60, seed: int = 20260911,
                  new_per_gen: int = 8, m0: int = 15,
                  persist: bool = True, state_path: Path = ENGINE_STATE_PATH,
                  reset_state: bool = False) -> dict:
    prev = {} if reset_state else _load_engine_state(state_path)
    # 每次运行推进种子，使各代探索新领地；同时由上一次运行的近失种子回流驱动，
    # 从而让"自进化"在运行之间真正累积学习，而非重复生成同一批候选。
    prev_runs = (prev.get("runs", 0) or 0) if not reset_state else 0
    eff_seed = seed + prev_runs * 7919
    arena = EvolutionArena(db, last_n, top_k, alpha, fdr_q, max_gens, prize, cost,
                           oos_n, eff_seed, new_per_gen, m0, prev_state=prev)
    report = arena.run()
    if persist:
        state = {
            "ledger": arena.ledger.to_dict(),
            "near_miss_seeds": [
                {"feats": l.get("feats"), "family": l.get("family")}
                for l in arena.lineage.values()
                if l.get("status") == "near_miss" and l.get("feats")
            ],
            "runs": arena.engine_runs,
            "last_generated_at": report["generated_at"],
            "last_score": report["directional"]["score"],
            "last_winner": report["final_verdict"]["winner"],
        }
        _save_engine_state(state, state_path)
    return report


def write_report(report: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)


def main():
    import argparse

    ap = argparse.ArgumentParser(description="自进化辩论擂台 / Evolution Arena")
    ap.add_argument("--db", default=str(ROOT / "sd3d_history.sqlite3"))
    ap.add_argument("--last-n", type=int, default=200)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--fdr-q", type=float, default=0.05)
    ap.add_argument("--max-gens", type=int, default=3)
    ap.add_argument("--oos-n", type=int, default=60)
    ap.add_argument("--new-per-gen", type=int, default=8)
    ap.add_argument("--prize", type=float, default=1040.0)
    ap.add_argument("--cost", type=float, default=2.0)
    ap.add_argument("--reset-state", action="store_true",
                    help="丢弃跨运行累积状态（账本/近失种子），从零开始")
    ap.add_argument("--no-persist", action="store_true",
                    help="本次运行不写回引擎状态文件（不影响已有状态）")
    ap.add_argument("--out", default=str(REPORTS / "evolution-arena-latest.json"))
    a = ap.parse_args()
    report = run_evolution(
        Path(a.db), a.last_n, a.top_k, a.alpha, a.fdr_q, a.max_gens,
        a.prize, a.cost, a.oos_n, 20260911, a.new_per_gen, 15,
        persist=not a.no_persist, reset_state=a.reset_state)
    write_report(report, Path(a.out))
    fv = report["final_verdict"]
    lg = report["ledger"]
    print(f"Wrote {a.out}")
    print(f"累计测试主张 {report['config']['max_gens']} 代 · FDR存活 {len(report['lineage']) and sum(1 for x in report['lineage'] if x['fitness']['fdr_survivor'])}")
    print(f"方向得分 score={report['directional']['score']} · 置信区间 {report['directional']['score_ci']}")
    print(f"正方 AP={lg['camps']['pro']['ap']:.1f} Rep={lg['camps']['pro']['rep']:.1f} · "
          f"反方 RP={lg['camps']['con']['rp']:.1f} Rep={lg['camps']['con']['rep']:.1f}")
    print(f"裁决: {fv['winner_label']}")
    print(f"结论: {fv['conclusion']}")


if __name__ == "__main__":
    main()
