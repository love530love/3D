"""角色执行器：把 roles.json 里声明的空壳角色变成可驱动的真实能力。

设计原则（与治理一致）：
- 每个执行器是纯函数，输入报告/状态/账本，输出结构化判定。
- **绝不直写引擎状态**：所有"提议"走 pending/队列，所有"变更"仍须经
  interventions / ledger 闸门（required_gate 不变量在 roles.json 强制）。
- 让"任意 AI 接入即驱动"成为现实：每个角色都有可被 CLI/引擎调用的入口。

角色与执行器映射：
  gatekeeper    -> gatekeeper_check        诚实闸门（离线自治时强制把关）
  replicator    -> replicator_run          对 FDR 存活主张做跨窗口独立复现
  bias_auditor  -> bias_audit              扫描治理账本/运行史的确认偏误
  ideator       -> ideator_suggest         提出新假设空间/特征原语
  archivist     -> archivist_index         萃取机构记忆（日志/历史近失）供新 AI 接入
  orchestrator  -> orchestrate_protocol    仅为协议说明（非守护进程）
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from workbench import evolution_arena as ea
from workbench import interventions as iv

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

BET_KEYWORDS = ["买", "下注", "投入", "稳赚", "包赚", "倍投", "跟单", "梭哈",
                "盈利策略", "保证收益", "必中", "一定中"]


# ===========================================================================
# gatekeeper：诚实闸门守门员
# ===========================================================================
def gatekeeper_check(report: dict) -> dict:
    """检查一份已生成的报告/输出是否诚实、不误导、不变相投注建议。

    离线自治时应在'写报告'之前调用；不通过则标记 gate_passed=False，
    由编排/人工决定是否修订后再发布。不修改报告本身。
    """
    issues: list[str] = []
    text = json.dumps(report, ensure_ascii=False)
    fv = report.get("final_verdict", {}) or {}
    d = report.get("directional", {}) or {}
    concl = fv.get("conclusion", "") or ""
    fdr_note = fv.get("fdr_note", "") or ""

    # 1) 免责声明：必须说明随机过程 / 非投注建议
    if not any(k in text for k in ["不构成投注建议", "不构成任何投注建议",
                                    "随机过程", "受监管随机", "不宣称"]):
        issues.append("缺少免责声明（未说明随机过程/非投注建议）")

    # 2) score 与裁决一致性：score 是点估计，是否显著以 CI/Fisher p 为准。
    #    仅当「方向显著为正(significant=True) 却判 random」才矛盾；
    #    点估计偏高但 CI 含 0（不显著）时裁决 random 是诚实的，此时只要输出
    #    显式标注了「点估计不显著、裁决依据 CI+OOS」即不算误导。
    score = d.get("score", 0.0) or 0.0
    significant = bool(d.get("significant", False))
    sig_note = d.get("significance_note", "") or ""
    verdict = fv.get("winner")
    if significant and verdict == "random":
        issues.append(
            f"方向得分显著为正(score={score:.3f}, CI 不含 0) 却裁决 random，呈现矛盾"
            f"（{sig_note}）")
    if score < -0.3 and verdict == "weak_signal":
        issues.append("方向得分与裁决矛盾（score<0 却判 weak_signal）")
    if (not significant) and verdict == "random" and not any(
            k in text for k in ["点估计", "CI 不含 0", "CI 含 0", "不显著", "显著性"]):
        issues.append(
            "裁决 random 但输出未显式标注'点估计不显著、裁决依据 CI+OOS 盲评'，"
            "易被误读为 score 与裁决自相矛盾")

    # 3) 变相投注建议扫描
    hit = [k for k in BET_KEYWORDS if k in concl or k in fdr_note]
    if hit:
        issues.append("检测到疑似投注建议用语：" + "/".join(hit))

    # 4) 开放探索姿态：random 结论不得写成'纯随机/探索终止'
    if verdict == "random":
        if ("纯随机" in concl or "完全随机" in concl) and \
           "探索" not in concl and "开放" not in concl and "未检出" not in concl:
            issues.append("裁决 random 但结论写作'纯随机/探索终止'口吻，违反开放探索姿态")

    honesty = round(max(0.0, 1.0 - 0.25 * len(issues)), 3)
    return {
        "role": "gatekeeper",
        "passed": len(issues) == 0,
        "honesty_score": honesty,
        "issues": issues,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


# ===========================================================================
# replicator：复现验证团
# ===========================================================================
def replicator_run(db_path: str | Path, windows: tuple[int, ...] = (120, 180, 240),
                   alpha: float = 0.05, top_k: int = 10) -> dict:
    """对最近一次进化报告中 FDR 存活的主张，做跨窗口独立复现。

    宪章要求'存活信号须经 OOS+独立复现'。本执行器在多个不同回看窗口下
    重算原始二项检验，统计主张在多少窗口里仍'显著优于随机基线'，给出
    复现率。合成/突变类主张若无稳定 predict 闭包则标记为'需人工重建'。
    """
    db = Path(db_path)
    nums = ea.load_numbers(db)
    total = len(nums)
    rep_path = REPORTS / "evolution-arena-latest.json"
    if not rep_path.exists():
        return {"role": "replicator", "error": "no evolution report found", "replications": []}
    report = json.loads(rep_path.read_text(encoding="utf-8"))
    lineage = report.get("lineage", [])
    survivors = [l for l in lineage if l.get("fitness", {}).get("fdr_survivor")]

    # 重建基桩主张（稳定 id，可定位 predict 闭包）
    base_claims = ea._build_pro_claims()
    base_by_id = {c["id"]: c for c in base_claims}

    replications = []
    for s in survivors:
        cid = s["claim_id"]
        bc = base_by_id.get(cid)
        if bc is None:
            replications.append({
                "claim_id": cid, "name": s.get("name"),
                "status": "ungrounded",
                "note": "合成/突变类存活主张，需重建 predict 闭包方可独立复现",
            })
            continue
        per_window = []
        for w in windows:
            start = max(1, total - w)
            end = total
            ev = ea.collect_evidence(bc, nums, start, end, top_k, alpha)
            if ev is None:
                per_window.append(None)
                continue
            per_window.append(ev["verdict"] == "显著优于随机基线")
        n_win = sum(1 for x in per_window if x is True)
        n_valid = sum(1 for x in per_window if x is not None)
        replications.append({
            "claim_id": cid, "name": s.get("name"),
            "status": "replicated" if n_win == n_valid and n_valid > 0 else "fragile",
            "replicated_in": f"{n_win}/{n_valid}",
            "raw_p_first_window": (ea.collect_evidence(bc, nums, max(1, total - windows[0]), total, top_k, alpha) or {}).get("two_sided_p"),
        })
    replicated = sum(1 for r in replications if r.get("status") == "replicated")
    fragile = sum(1 for r in replications if r.get("status") == "fragile")
    result = {
        "role": "replicator",
        "n_survivors": len(survivors),
        "n_replicated": replicated,
        "n_fragile": fragile,
        "replication_rate": round(replicated / len(survivors), 3) if survivors else None,
        "replications": replications,
        "windows": list(windows),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    # 落盘：与 structure_tests/external_coupling/near_miss_ensemble 一致，供大屏 + 引擎状态读取
    try:
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "replication-latest.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return result


# ===========================================================================
# bias_auditor：偏差审计团
# ===========================================================================
def bias_audit(jsonl_path: str | Path | None = None) -> dict:
    """扫描治理账本(interventions.jsonl)与运行史，识别确认偏误/cherry-pick/
    阈值突变/反复无理由 reset。人类式怀疑精神的自动化。"""
    p = Path(jsonl_path) if jsonl_path else (REPORTS / "interventions.jsonl")
    flags: list[str] = []
    if not p.exists():
        return {"role": "bias_auditor", "flags": ["无干预账本（治理层休眠，尚未被真实运行调用）"],
                "checked_at": datetime.now().isoformat(timespec="seconds")}
    recs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    # ① cherry-pick：只接受"支持可预测"的干预、拒绝"不利"的
    overrides = [r for r in recs if r.get("action") == "override_verdict"]
    if overrides:
        kept = sum(1 for r in overrides if r.get("decision") == "accept")
        rejected = sum(1 for r in overrides if r.get("decision") == "reject")
        if kept > 0 and rejected == 0:
            flags.append(f"疑似 cherry-pick：{kept} 次推翻裁决均被接受、0 次被拒")
    # ② 阈值突变：同一参数被反复、无正当理由地改来改去
    from collections import Counter, defaultdict
    param_changes = [r for r in recs if r.get("action") == "param_change"]
    by_param = defaultdict(list)
    for r in param_changes:
        for ch in r.get("changes", []):
            by_param[ch.get("name")].append(r.get("decision"))
    for name, decs in by_param.items():
        if len(decs) >= 3:
            flags.append(f"参数 {name} 被变更 {len(decs)} 次，检查是否阈值漂移/cherry-pick")
    # ③ 重置滥用
    resets = [r for r in recs if r.get("action") == "reset"]
    if len(resets) >= 3:
        flags.append(f"重置操作 {len(resets)} 次，检查是否'重置滥用'（逃避稳态检查）")
    return {
        "role": "bias_auditor",
        "n_records": len(recs),
        "flags": flags or ["未检出明显偏差信号"],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


# ===========================================================================
# ideator：设想头脑风暴团
# ===========================================================================
def ideator_suggest(last_n: int = 200) -> dict:
    """提出新假设空间/特征原语（'万一有效'）。与 promoter 精炼已知区分：
    这里是发明未知疆域，而非重提已知近失。返回提案供裁判/治理层评估。"""
    # 当前特征原语池（进化引擎已用）
    used = set(ea.FEAT_POOL) if hasattr(ea, "FEAT_POOL") else set()
    # 候选新原语（更高阶/跨域），供探索"万一有效"
    candidates = [
        {"primitive": "order3_markov", "space": "高阶马尔可夫（t 对 t-1,t-2,t-3 联合）",
         "rationale": "当前仅 order-1/order-2；三阶可捕捉更长程位间依赖"},
        {"primitive": "perm_entropy", "space": "符号动力学/排列熵",
         "rationale": "检测开奖序列的不可预测性结构，比命中率更敏感"},
        {"primitive": "lz_complexity", "space": "Lempel-Ziv 压缩复杂度",
         "rationale": "衡量序列规则性，弱信号敏感"},
        {"primitive": "bayes_sparse", "space": "贝叶斯稀疏效应搜索",
         "rationale": "对微小效应比 BH-FDR 更灵敏"},
        {"primitive": "active_retest", "space": "主动/自适应实验设计",
         "rationale": "针对近失联结放大复测，而非被动随机生成"},
        {"primitive": "lunar_calendar", "space": "农历/节气外部耦合",
         "rationale": "external_coupling 仅占日历域，农历是下一域"},
    ]
    novel = [c for c in candidates if c["primitive"] not in used]
    return {
        "role": "ideator",
        "already_used_primitives": sorted(used),
        "proposals": novel,
        "count": len(novel),
        "note": "提案须经裁判团+守门员评估、并经 interventions 闸门方可纳入特征空间",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


# ===========================================================================
# archivist：档案知识管理团
# ===========================================================================
def archivist_index() -> dict:
    """萃取机构记忆，让任意 AI 接入不归零：读取反思日志、历史近失、审计结论，
    产出一份'新 AI 上手须知'索引。"""
    journal_path = REPORTS / "selfdrive-journal.json"
    entries: list[dict] = []
    if journal_path.exists():
        try:
            entries = json.loads(journal_path.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    # 最近近失（来自最近进化报告）
    rep_path = REPORTS / "evolution-arena-latest.json"
    near_misses = []
    if rep_path.exists():
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        near_misses = [l["claim_id"] for l in rep.get("lineage", [])
                       if l.get("status") == "near_miss"][-10:]
    last_thought = entries[-1].get("thought", "") if entries else ""
    best_mode = (max(entries, key=lambda e: e.get("fitness", 0)) or {}).get("mode") if entries else None
    return {
        "role": "archivist",
        "batches_logged": len(entries),
        "latest_reflection": last_thought,
        "best_strategy_mode": best_mode,
        "tracked_near_misses": near_misses,
        "onboarding": "新 AI 应先读 ROLES.md 与 selfdrive-journal.json，理解项目以"
                      "'诚实探索、开放姿态、跨运行累积'为第一原则；任何状态写入须经治理闸。",
        "indexed_at": datetime.now().isoformat(timespec="seconds"),
    }


# ===========================================================================
# orchestrator：编排调度团（仅为协议，非守护进程）
# ===========================================================================
def orchestrate_protocol() -> dict:
    """返回标准自驱动流程协议。任意 AI 均可按此充当一次性编排者，无需特权。"""
    return {
        "role": "orchestrator",
        "protocol": [
            "1. checkpoint.snapshot() 打点（失败可还原）",
            "2. predictive_eval 预测竞技场 + debate_arena 对抗辩论（入口）",
            "3. evolution_arena 自进化元循环（含断点#1 近失回流）",
            "4. gatekeeper_check(report) 诚实闸门——不通过则修订后再发布",
            "5. replicator_run 对存活主张跨窗口复现",
            "6. selfdrive 反思日志（thinking-journal 自适应下一轮策略）",
            "7. archivist_index 更新机构记忆；bias_audit 抽查治理账本",
            "8. dashboard 重建；若 fitness 显著劣化则 checkpoint.restore 回滚",
        ],
        "note": "仅为规范/协议；任何 AI 按 ROLES.md 即可驱动，无中心守护进程。",
    }


def run_role(role_id: str, **kwargs: Any) -> dict:
    """统一入口：role_id -> 对应执行器。供 CLI/引擎/任意 AI 调用。

    gatekeeper 若未显式给 report，自动读取最近进化报告（让 CLI 免参可用）。
    """
    if role_id == "gatekeeper" and "report" not in kwargs:
        ep = REPORTS / "evolution-arena-latest.json"
        kwargs["report"] = json.loads(ep.read_text(encoding="utf-8")) if ep.exists() else {}
    table = {
        "gatekeeper": lambda: gatekeeper_check(kwargs.get("report", {})),
        "replicator": lambda: replicator_run(kwargs.get("db", ROOT / "sd3d_history.sqlite3")),
        "bias_auditor": lambda: bias_audit(kwargs.get("jsonl_path")),
        "ideator": lambda: ideator_suggest(kwargs.get("last_n", 200)),
        "archivist": lambda: archivist_index(),
        "orchestrator": lambda: orchestrate_protocol(),
    }
    if role_id not in table:
        return {"role": role_id, "error": "unknown role executor"}
    return table[role_id]()
