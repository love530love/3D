"""selfdrive.py — 自驱动进化引擎（离线可跑，无需人在环）.

把"预测"与"对抗"作为入口，驱动进化引擎，并通过深度反思日志(思考日志)自适应下一轮策略。
体现三种智能：
  * ai（人工智能）   —— predictive_eval 模型竞技场、debate_arena 对抗辩论、evolution_arena 元循环
  * human（类人智能）—— referee/gatekeeper 的评判与诚实闸门（经 interventions 治理层）
  * deep（深度思维） —— 反思日志：批后反思"学到什么/下一步试什么"，按历史 fitness 选最优策略

安全网：每批探索前 checkpoint 打点；若本批 fitness 相对上批回归，则 rollback 还原重试，
彻底满足"探索失败却无法还原"的防护要求。任意 AI 或离线定时任务都可调用本模块。

用法：
  python -m workbench.selfdrive run --label batch-001 --mode standard
  python -m workbench.selfdrive run --label batch-002 --mode aggressive
  python -m workbench.selfdrive journal        # 查看深度思考日志
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from . import checkpoint
from . import roles as role_registry

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
DB = ROOT / "sd3d_history.sqlite3"
ENGINE_STATE = REPORTS / "evolution-engine-state.json"
JOURNAL = REPORTS / "thinking-journal.jsonl"
STRATEGY_BOOK = REPORTS / "strategy-book.json"

MODES = {
    "standard":   {"max_gens": 3, "new_per_gen": 8, "oos_n": 60},
    "aggressive": {"max_gens": 4, "new_per_gen": 14, "oos_n": 90},
    "conservative": {"max_gens": 2, "new_per_gen": 5, "oos_n": 40},
}


# ---------------------------------------------------------------------------
# 智能指标（fitness）——衡量"本批探索收获"，非投注收益
# ---------------------------------------------------------------------------
def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def fitness_from_state() -> dict:
    """从当前报告/状态估算本批探索收获（方法学健康度，非盈利）。"""
    evo = _read_json(REPORTS / "evolution-arena-latest.json") or {}
    state = _read_json(ENGINE_STATE) or {}
    pred = _read_json(REPORTS / "predictive-arena-latest.json") or {}
    debate = _read_json(REPORTS / "debate-arena-latest.json") or {}

    ledger_claims = len((state.get("ledger") or {}).get("claims", {}))
    near_miss = len(state.get("near_miss_seeds", []) or [])
    directional = (evo.get("directional") or {}).get("score", 0.0) or 0.0
    winner = (evo.get("final_verdict") or {}).get("winner", "random")
    oos_survivors = len((evo.get("oos") or {}).get("survivors", []) or [])

    # 预测竞技场：最佳方案在 OOS 上的命中率（若有）
    best_hit = 0.0
    for s in (pred.get("schemes") or []):
        hr = s.get("oos_exact_rate") or 0.0
        if hr and hr > best_hit:
            best_hit = hr
    debate_edges = len((debate.get("edges") or []) if isinstance(debate.get("edges"), list) else [])

    fitness = (
        ledger_claims * 0.05
        + near_miss * 1.0
        + (10.0 if oos_survivors > 0 else 0.0)
        + max(0.0, directional) * 5.0
        + best_hit * 50.0
        + debate_edges * 0.2
    )
    return {
        "fitness": round(fitness, 3),
        "ledger_claims": ledger_claims,
        "near_miss": near_miss,
        "directional": round(directional, 4),
        "winner": winner,
        "oos_survivors": oos_survivors,
        "best_predict_hit": round(best_hit, 4),
        "debate_edges": debate_edges,
    }


# ---------------------------------------------------------------------------
# 深度思考日志（deep thinking）
# ---------------------------------------------------------------------------
def reflection_journal_append(entry: dict) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_journal() -> list[dict]:
    if not JOURNAL.exists():
        return []
    out = []
    for line in JOURNAL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _load_strategy_book() -> dict:
    return _read_json(STRATEGY_BOOK) or {}


def _save_strategy_book(book: dict) -> None:
    STRATEGY_BOOK.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")


def _best_mode() -> str:
    """深度思维：按历史 fitness 选迄今最优策略模式。"""
    book = _load_strategy_book()
    if not book:
        return "standard"
    best, best_f = "standard", -1.0
    for mode, rec in book.items():
        f = rec.get("best_fitness", -1.0)
        if f > best_f:
            best, best_f = mode, f
    return best


# ---------------------------------------------------------------------------
# 单批自驱动（离线可跑）
# ---------------------------------------------------------------------------
def run_batch(label: str, mode: str = "standard", last_n: int = 200, top_k: int = 10,
              alpha: float = 0.1, fdr_q: float = 0.05, allow_rollback: bool = True) -> dict:
    mode = mode if mode in MODES else "standard"
    m = MODES[mode]
    ts = datetime.now().isoformat(timespec="seconds")

    # 0) 任意 AI 可读取角色契约（自描述）——证明"无需特定对话记忆即可驱动"
    roles = role_registry.list_roles()
    role_ids = [r["id"] for r in roles]

    # 1) 安全网：探索前打点
    pre = fitness_from_state()
    ck = checkpoint.snapshot(f"pre-{label}", notes=f"mode={mode}", fitness=pre["fitness"])

    log: list[str] = [f"[{ts}] batch {label} mode={mode} start; roles discoverable={len(role_ids)}"]
    log.append(f"pre-batch fitness={pre['fitness']} (claims={pre['ledger_claims']}, near_miss={pre['near_miss']})")

    # 2) 预测入口（ai）：模型竞技场严格时间前向回测
    try:
        from .predictive_eval import run_arena as _pred
        _pred(DB, last_n=min(last_n, 200), top_k=top_k, alpha=alpha)
        log.append("predictive arena: done")
    except Exception as e:
        log.append(f"predictive arena: SKIP ({e})")

    # 3) 对抗入口（ai + human）：双阵营辩论擂台
    try:
        from .debate_arena import run_debate as _deb
        _deb(DB, last_n=min(last_n, 200), top_k=top_k, alpha=alpha, fdr_q=fdr_q,
             max_rounds=4, prize=1040.0, cost=2.0)
        log.append("debate arena: done")
    except Exception as e:
        log.append(f"debate arena: SKIP ({e})")

    # 4) 进化引擎（ai + human + deep）：跨运行累积 + 近失回流
    try:
        from .evolution_arena import run_evolution as _evo
        _evo(DB, last_n=last_n, top_k=top_k, alpha=alpha, fdr_q=fdr_q,
             max_gens=m["max_gens"], oos_n=m["oos_n"], new_per_gen=m["new_per_gen"],
             persist=True, reset_state=False)
        log.append("evolution arena: done")
    except Exception as e:
        log.append(f"evolution arena: ERROR ({e})")

    # 5) 评估 & 深度反思
    post = fitness_from_state()
    regressed = allow_rollback and post["fitness"] < pre["fitness"]

    if regressed:
        # 还原重试：本批探索失败/走错方向 -> rollback 到探索前
        rb = checkpoint.restore(ck["id"], confirm=True)
        log.append(f"REGRESSION detected (post={post['fitness']} < pre={pre['fitness']}) -> rollback: {rb.get('log')}")
        post = fitness_from_state()  # 还原后重读

    # 6) 深度思考：把本批经验写入反思日志，并自适应下一轮策略
    entry = {
        "ts": ts, "label": label, "mode": mode,
        "pre_fitness": pre["fitness"], "post_fitness": post["fitness"],
        "regressed": regressed, "rolled_back": regressed,
        "metrics": post,
        "thought": _reflect(mode, pre, post, regressed),
        "next_strategy": _adapt_strategy(mode, post, regressed),
    }
    reflection_journal_append(entry)

    # 更新策略书（深度思维：记住各模式历史最优）
    book = _load_strategy_book()
    rec = book.get(mode, {"best_fitness": -1.0, "runs": 0})
    rec["runs"] = rec.get("runs", 0) + 1
    if post["fitness"] > rec.get("best_fitness", -1.0):
        rec["best_fitness"] = post["fitness"]
        rec["best_label"] = label
    book[mode] = rec
    _save_strategy_book(book)

    # 7) 重建大屏（让人类/任意 AI 能看到）
    try:
        from . import engine, dashboard
        html = dashboard.build_html(engine.collect_state(), live=True)
        (ROOT / "dashboard.html").write_text(html, encoding="utf-8")
        log.append("dashboard rebuilt")
    except Exception as e:
        log.append(f"dashboard rebuild SKIP ({e})")

    log.append(f"batch {label} done; post_fitness={post['fitness']}; next_mode={entry['next_strategy']}")
    return {"ok": True, "log": log, "entry": entry, "checkpoint": ck["id"]}


def _reflect(mode: str, pre: dict, post: dict, regressed: bool) -> str:
    if regressed:
        return (f"本批({mode})相对上批回归：探索未带来额外方法学收获，已 rollback 还原重试。"
                f"可能该模式在当前样本下已过拟合或撞上噪声，应换更稳的策略。")
    delta = round(post["fitness"] - pre["fitness"], 3)
    if post["winner"] == "weak_signal":
        return (f"本批探出 weak_signal 方向；near_miss={post['near_miss']}，"
                f"OOS存活={post['oos_survivors']}。需复现团独立复核，勿急于下'可预测'定论。")
    return (f"本批(mode={mode})收获 delta_fitness={delta}；near_miss={post['near_miss']}，"
            f"预测最佳OOS命中={post['best_predict_hit']}。当前仍属'未检出可区分信号'的开放探索态，"
            f"按宪章继续追踪弱信号，不预设不可预测。")


def _adapt_strategy(mode: str, post: dict, regressed: bool) -> str:
    book = _load_strategy_book()
    # 若本批回归，下一轮换一个模式；否则坚持当前模式，长期由 best_mode() 择优
    if regressed:
        for cand in ("conservative", "standard", "aggressive"):
            if cand != mode:
                return cand
    return _best_mode()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="自驱动进化引擎（离线可跑）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="运行一批自驱动探索")
    r.add_argument("--label", required=True)
    r.add_argument("--mode", choices=list(MODES.keys()), default="standard")
    r.add_argument("--last-n", type=int, default=200)
    r.add_argument("--top-k", type=int, default=10)
    r.add_argument("--alpha", type=float, default=0.1)
    r.add_argument("--fdr-q", type=float, default=0.05)
    r.add_argument("--no-rollback", action="store_true", help="关闭回归回滚")

    sub.add_parser("journal", help="查看深度思考日志")
    sub.add_parser("best-mode", help="查看当前最优策略模式")

    args = ap.parse_args()
    if args.cmd == "run":
        res = run_batch(args.label, args.mode, args.last_n, args.top_k,
                        args.alpha, args.fdr_q, allow_rollback=not args.no_rollback)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "journal":
        print(json.dumps(load_journal(), ensure_ascii=False, indent=2))
    elif args.cmd == "best-mode":
        print(json.dumps({"best_mode": _best_mode(), "strategy_book": _load_strategy_book()},
                         ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
