"""人工干预治理层（「人机协作稳定性约定」②④⑥ 的工程实现）.

把"人类调整参数 / 加入影响因子 / 推翻裁决 / 重置"变成一条**结构化、可审计、带自保护**的通道：

  * 人类只能以「干预请求」形式提交，不能静默改写系统；
  * 每次干预按风险分级 L0(只读)→L1(普通参数)→L2(高风险数据/模型/因子)→L3(宪章)；
  * 自保护(稳态)检查：泄漏检测、显著性膨胀、重置滥用、无证据的裁决推翻、cherry-pick；
  * 决定：accept(应用并持久化) / quarantine(记录但不应用，待复核) / reject(记录并拒绝)；
  * 全部 append-only 写入 reports/interventions.jsonl，不可篡改。

进化隐喻：这是系统的"自主神经系统"——在创造者（人）可能出错/带偏置时，维持内部稳态，
既不让人的不稳定污染系统，又为人 legitimate 的"what if"好奇心留出受控入口。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
INTERVENTIONS_LOG = REPORTS / "interventions.jsonl"
OVERRIDES_FILE = REPORTS / "engine-overrides.json"
FACTOR_REGISTRY = REPORTS / "engine-factor-registry.json"

# 允许的声明式因子 kind（纯单 draw 函数，无泄漏、可序列化）
# a/b/pos ∈ {0,1,2}；m/v/diff 为整数。系统只接受这些，杜绝任意代码注入。
DECL_KINDS = {"pos_parity_eq", "sum_mod_eq", "digit_at", "span_mod_eq", "pos_diff_eq"}

# 参数覆盖的合法范围（超出则拒绝，防越界/无意义值）
PARAM_RANGES = {
    "last_n": (20, 2000), "top_k": (1, 100), "alpha": (0.001, 0.1),
    "fdr_q": (0.001, 0.1), "max_gens": (1, 20), "prize": (0, 100000),
    "cost": (0, 1000), "oos_n": (0, 500), "new_per_gen": (1, 50), "m0": (1, 200),
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ===========================================================================
# 干预请求
# ===========================================================================
def make_intervention(itype: str, by: str, after=None, rationale: str = "",
                      before=None, spec: dict | None = None) -> dict:
    return {
        "id": f"iv_{int(datetime.now().timestamp() * 1000)}",
        "type": itype,          # param_change | add_factor | override_verdict | reset
        "by": by,
        "before": before,
        "after": after,          # dict(参数->值) for param_change；None otherwise
        "spec": spec,            # dict for add_factor
        "rationale": rationale,
        "created_at": _now(),
    }


# ===========================================================================
# 风险分级
# ===========================================================================
def classify(it: dict) -> str:
    t = it["type"]
    if t == "param_change":
        fields = set((it.get("after") or {}).keys())
        risky = {"alpha", "fdr_q", "prize", "cost", "oos_n"} & fields
        return "L2" if risky else "L1"
    if t in ("add_factor", "override_verdict"):
        return "L2"
    if t == "reset":
        return "L1"
    return "L1"


# ===========================================================================
# 自保护(稳态)检查
# ===========================================================================
def risk_checks(it: dict, recent_resets: int = 0) -> list[tuple]:
    notes: list[tuple] = []
    t = it["type"]

    # 1) 泄漏检测：add_factor 必须是纯单 draw 声明式因子，位置限定 0..2
    if t == "add_factor":
        spec = it.get("spec") or {}
        kind = spec.get("kind")
        if kind not in DECL_KINDS:
            notes.append(("leakage_or_unknown_kind", "high", False,
                          f"未知/不可序列化因子 kind={kind}；仅允许 {sorted(DECL_KINDS)}"))
        else:
            bad = False
            for k in ("a", "b", "pos"):
                v = spec.get(k)
                if v is not None and not (0 <= int(v) <= 2):
                    notes.append(("leakage_pos_range", "high", False, f"{k}={v} 超出合法位置 0..2"))
                    bad = True
            blob = json.dumps(spec, ensure_ascii=False).lower()
            if "train" in blob or "future" in blob or "next" in blob:
                notes.append(("leakage_ref", "high", False, "因子 spec 不得引用训练/未来数据"))
                bad = True
            if not bad:
                notes.append(("leakage_or_unknown_kind", "info", True,
                              "声明式 DSL，纯单 draw 函数，无泄漏"))

    # 2) 显著性膨胀：提高 alpha / fdr_q 阈值（放宽为更易"显著"）
    if t == "param_change":
        after = it.get("after") or {}
        a = after.get("alpha", 0)
        q = after.get("fdr_q", 0)
        if (a and a > 0.1) or (q and q > 0.1):
            notes.append(("significance_inflation", "medium", False,
                          f"提高 alpha/fdr_q 至 {a}/{q} 会膨胀显著性，需明确理由"))
        else:
            notes.append(("significance_inflation", "info", True, "阈值在安全范围(≤0.1)"))

    # 3) 重置滥用（稳态）：短时间内多次 reset = 用重置抹除跨运行累积
    if t == "reset":
        if recent_resets >= 2:
            notes.append(("reset_abuse", "high", False,
                          f"近 24h 已重置 {recent_resets} 次，疑似用 reset 抹除累积（稳态保护触发）"))
        else:
            notes.append(("reset_abuse", "info", True, "重置频率正常"))

    # 4) 无证据的裁决推翻
    if t == "override_verdict":
        if not it.get("rationale") or len(it.get("rationale", "")) < 20:
            notes.append(("override_without_evidence", "high", False,
                          "推翻引擎裁决需附≥20字可复现证据(如 FDR 存活的重测)；否则视为无证据推翻"))
        else:
            notes.append(("override_without_evidence", "info", True, "已附理由"))

    # 5) cherry-pick：按 id 单独提拔某个近失，却无新证据
    if t == "override_verdict" and it.get("after", {}).get("claim_id"):
        notes.append(("cherry_pick", "medium", False,
                      "按 claim_id 单独提拔近失属于 cherry-pick；须经独立 FDR 重测方可接受"))

    return notes


# ===========================================================================
# 决定
# ===========================================================================
def decide(it: dict, recent_resets: int = 0):
    tier = classify(it)
    checks = risk_checks(it, recent_resets)
    highs = [c for c in checks if c[1] == "high" and not c[2]]
    if highs:
        # 裁决推翻/重置 若出现 high 风险 → 直接 reject；其余 high → quarantine
        status = "reject" if it["type"] in ("override_verdict", "reset") and highs else "quarantine"
        reasons = [f"[{c[0]}] {c[3]}" for c in highs]
        return tier, status, reasons, checks
    # L2 必须有理由
    if tier == "L2" and not it.get("rationale"):
        return tier, "quarantine", ["L2 干预需附理由，待人工复核"], checks
    return tier, "accept", [], checks


# ===========================================================================
# 应用（仅 accept 才落地）
# ===========================================================================
def _valid_param(k: str, v) -> bool:
    if k not in PARAM_RANGES:
        return False
    lo, hi = PARAM_RANGES[k]
    try:
        return lo <= float(v) <= hi
    except Exception:
        return False


def apply_param_override(after: dict) -> dict:
    ov: dict = {}
    if OVERRIDES_FILE.exists():
        try:
            ov = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
        except Exception:
            ov = {}
    for k, v in (after or {}).items():
        if _valid_param(k, v):
            ov[k] = v
    OVERRIDES_FILE.write_text(json.dumps(ov, ensure_ascii=False, indent=2), encoding="utf-8")
    return ov


def register_factor(spec: dict, by: str) -> str:
    reg: list = []
    if FACTOR_REGISTRY.exists():
        try:
            reg = json.loads(FACTOR_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            reg = []
    fid = f"uf_{len(reg)}_{spec.get('kind')}"
    reg.append({"id": fid, "spec": spec, "by": by, "created_at": _now()})
    FACTOR_REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    return fid


# ===========================================================================
# 账本（append-only）
# ===========================================================================
def record(it: dict, tier: str, status: str, reasons: list) -> dict:
    it = dict(it)
    it["tier"] = tier
    it["status"] = status
    it["reasons"] = reasons
    it["decided_at"] = _now()
    INTERVENTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(INTERVENTIONS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return it


def count_recent_resets(hours: int = 24) -> int:
    if not INTERVENTIONS_LOG.exists():
        return 0
    now = datetime.now().timestamp()
    n = 0
    for line in INTERVENTIONS_LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("type") == "reset":
            try:
                ts = datetime.fromisoformat(r["created_at"]).timestamp()
                if now - ts <= hours * 3600:
                    n += 1
            except Exception:
                pass
    return n


def load_overrides() -> dict:
    if not OVERRIDES_FILE.exists():
        return {}
    try:
        return json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_factor_registry() -> dict:
    if not FACTOR_REGISTRY.exists():
        return {}
    try:
        reg = json.loads(FACTOR_REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {e["id"]: e["spec"] for e in reg if "id" in e and "spec" in e}


def handle(it: dict) -> tuple[dict, list]:
    """提交一次干预：分级 → 稳态检查 → 决定 → 记录(append-only) → 若 accept 则落地。"""
    recent = count_recent_resets()
    tier, status, reasons, checks = decide(it, recent)
    it = record(it, tier, status, reasons)
    if status == "accept":
        if it["type"] == "param_change":
            apply_param_override(it["after"])
        elif it["type"] == "add_factor":
            register_factor(it["spec"], it["by"])
    return it, checks


def main():
    import argparse
    ap = argparse.ArgumentParser(description="人工干预治理通道（结构化/可审计/带自保护）")
    ap.add_argument("action", choices=["param_change", "add_factor", "override_verdict", "reset"],
                    help="干预类型")
    ap.add_argument("--by", default="user", help="操作者标识")
    ap.add_argument("--set", default="", help="param_change: key=val,key=val")
    ap.add_argument("--spec", default="", help="add_factor: JSON 声明式因子 spec")
    ap.add_argument("--why", default="", help="理由（L2 必填，≥20字以推翻裁决）")
    ap.add_argument("--claim", default="", help="override_verdict: 被提拔的 claim_id")
    a = ap.parse_args()
    if a.action == "param_change":
        after = {}
        for kv in a.set.split(","):
            kv = kv.strip()
            if not kv:
                continue
            k, v = kv.split("=", 1)
            after[k.strip()] = float(v) if "." in v or v.isdigit() else v
        it = make_intervention("param_change", a.by, after=after, rationale=a.why)
    elif a.action == "add_factor":
        import json as _j
        spec = _j.loads(a.spec)
        it = make_intervention("add_factor", a.by, spec=spec, rationale=a.why)
    elif a.action == "override_verdict":
        it = make_intervention("override_verdict", a.by,
                               after={"claim_id": a.claim}, rationale=a.why)
    else:
        it = make_intervention("reset", a.by, rationale=a.why)
    rec, checks = handle(it)
    print(f"干预 {rec['id']} → 分级 {rec['tier']} · 决定 {rec['status']}")
    for c in checks:
        print(f"  [{c[1]}] {c[0]}: {'通过' if c[2] else '未过'} — {c[3]}")
    if rec["reasons"]:
        print("拒绝/隔离理由:", "; ".join(rec["reasons"]))
    print(f"已 append-only 记录至 {INTERVENTIONS_LOG}")


if __name__ == "__main__":
    main()
