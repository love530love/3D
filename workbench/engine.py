"""Engine: orchestration + state collection for the workbench.

Pure standard library. Runs the existing pipeline scripts as subprocesses and
reads their latest reports to build a single state object consumed by the
dashboard. Never mutates data on its own except through the governed scripts.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .registry import (
    BACKUPS,
    DB,
    DECISIONS,
    FUNCTIONS,
    PRED,
    REPORTS,
    ROOT,
    by_id,
    resolve_args,
)

# Latest report files we surface on the dashboard.
LATEST_REPORTS = [
    "brain-decision-latest.json",
    "model-gate-latest.json",
    "drift-latest.json",
    "leakage-latest.json",
    "quality-latest.json",
    "probability-latest.json",
    "model-comparison-latest.json",
    "models-latest.json",
    "model-screening-latest.json",
    "outcomes-analysis-latest.json",
    "randomness-latest.json",
    "backtest-latest.json",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_function(func_id: str, extra_args=None, on_line=None) -> dict:
    """Run a registered function. Returns {returncode, log, produced}.

    on_line is an optional callback(str) invoked for each output line (used by
    the live server to stream logs).
    """
    func = by_id(func_id)
    if func is None:
        return {"returncode": 2, "log": [f"ERROR: unknown function id '{func_id}'"], "produced": []}
    if func["script"] == "__rollback__":
        return {"returncode": 2, "log": ["ERROR: use rollback(ref) directly, not run_function"], "produced": []}
    if func["script"] == "__compare_pending__":
        return _run_compare_pending(on_line)
    if func["script"] == "__multi_method__":
        return _run_multi_method(extra_args, on_line)
    if func["script"] == "__history_stats__":
        return _run_history_stats(extra_args, on_line)

    script_path = ROOT / func["script"]
    if not script_path.exists():
        return {"returncode": 1, "log": [f"ERROR: script not found: {script_path}"], "produced": []}

    cmd = [sys.executable, str(script_path), *resolve_args(func["args"])]
    if extra_args:
        cmd += list(extra_args)
    log: list[str] = []
    log.append("CMD: " + " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            log.append(line)
            if on_line:
                on_line(line)
        rc = proc.wait()
    except Exception as exc:  # pragma: no cover - defensive
        return {"returncode": 1, "log": log + [f"ERROR: {exc}"], "produced": []}
    return {"returncode": rc, "log": log, "produced": []}


def _run_compare_pending(on_line=None) -> dict:
    log: list[str] = []
    if not PRED.exists():
        return {"returncode": 0, "log": ["No predictions directory."], "produced": []}
    pending = []
    for p in sorted(PRED.glob("frozen-*.json")):
        if "-comparison" in p.name:
            continue
        if not p.with_name(p.stem + "-comparison.json").exists():
            pending.append(p)
    if not pending:
        msg = "No pending predictions to compare."
        log.append(msg)
        if on_line:
            on_line(msg)
        return {"returncode": 0, "log": log, "produced": []}
    rc_all = 0
    for p in pending:
        cmd = [sys.executable, str(ROOT / "compare_prediction.py"), str(p), "--db", str(DB)]
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (r.stdout + r.stderr).strip()
        log.append(f"== {p.name} ==")
        log.append(out)
        if on_line:
            on_line(f"== {p.name} ==")
            on_line(out)
        if r.returncode not in (0, 2):
            rc_all = r.returncode
    return {"returncode": rc_all, "log": log, "produced": []}


def _run_multi_method(extra_args=None, on_line=None) -> dict:
    """Generate the multi-method comparison report (多种预测方式共存对比)."""
    import argparse

    from . import forecasts as fm

    ap = argparse.ArgumentParser()
    ap.add_argument("--last-n", type=int, default=12)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--history-offset", type=int, default=2)
    try:
        a = ap.parse_args(extra_args or [])
    except SystemExit:
        return {"returncode": 2, "log": ["参数解析失败（multi_method）。"], "produced": []}

    log: list[str] = []
    try:
        report = fm.build_report(DB, last_n=a.last_n, top_k=a.top_k, alpha=a.alpha, history_offset=a.history_offset)
    except Exception as exc:  # pragma: no cover - defensive
        return {"returncode": 1, "log": [f"生成多方法对比失败: {exc}"], "produced": []}

    out = REPORTS / "multi-method-latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.append(f"Wrote {out}")

    lp = report.get("last_period_compare") or {}
    log.append(f"最近一期 期号={report.get('last_period')} 实开={report.get('actual_last')}")
    for m in lp.get("methods", []):
        met = m.get("metrics") or {}
        top1 = (m.get("candidates") or ["-"])[0]
        log.append(
            f"  {m['method_id']:<28} top1={top1} 精确={met.get('exact_hit')} "
            f"位命中={met.get('position_top1_hits')} 偏差={met.get('digit_divergence')}"
        )
    np = report.get("next_period") or {}
    log.append(f"下期预测 期号={np.get('period')}（基于截至 {np.get('trained_on_periods_up_to')}）共 {len(np.get('methods', []))} 种方法")
    hc = report.get("historical_compare") or {}
    log.append(f"历史对照 期号={hc.get('period')} 实开={hc.get('actual')}（偏移 {report.get('history_offset')} 期）")
    wa = report.get("window_aggregate") or {}
    log.append(f"近 {wa.get('window_size')} 期严格时间顺序聚合:")
    for mid, s in (wa.get("per_method") or {}).items():
        ll = f"{s['mean_log_loss']:.3f}" if s.get("mean_log_loss") is not None else "-"
        log.append(
            f"  {mid:<28} 精确率={s['exact_rate']*100:5.1f}% "
            f"均位命中={s['mean_position_top1']*100:5.1f}% 均偏差={s['mean_digit_divergence']:.2f} ll={ll}"
        )
    log.append(f"备注: {wa.get('disclaimer','')}")

    if on_line:
        for line in log:
            on_line(line)
    return {"returncode": 0, "log": log, "produced": ["multi-method-latest.json"]}


def _run_history_stats(extra_args=None, on_line=None) -> dict:
    """Generate the human-facing historical & official-style statistics report."""
    import argparse

    from . import history_stats as hs

    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--pred-window", type=int, default=20)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--alpha", type=float, default=0.1)
    try:
        a = ap.parse_args(extra_args or [])
    except SystemExit:
        return {"returncode": 2, "log": ["参数解析失败（history_stats）。"], "produced": []}

    log: list[str] = []
    try:
        report = hs.build_report(
            DB, window=a.window, pred_window=a.pred_window, top_k=a.top_k, alpha=a.alpha
        )
    except Exception as exc:  # pragma: no cover - defensive
        return {"returncode": 1, "log": [f"生成历史与统计失败: {exc}"], "produced": []}

    if report.get("error"):
        return {"returncode": 1, "log": [f"无数据: {report.get('error')}"], "produced": []}

    out = REPORTS / "history-stats-latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.append(f"Wrote {out}")
    log.append(f"配置: {report['config']} · 回看 {report['count']} 期")
    log.append(
        f"和值分布样例: { {k: v for k, v in list(report['sum_distribution'].items()) if v} }"
    )
    log.append(f"组选类型: {report['type_stats']}")
    log.append(
        f"冷热(近{report['hot_cold']['n']}期, 期望{report['hot_cold']['expected']}): "
        + " ".join(f"{r['digit']}:{r['count']}{'▲' if r['cls']=='hot' else ('▼' if r['cls']=='cold' else '')}" for r in report['hot_cold']['ranked'])
    )
    pr = report["prediction_rolling"]
    log.append(f"历史预测滚动对照: {len(pr['periods'])} 期 × {len(pr['methods'])} 方法")
    if on_line:
        for line in log:
            on_line(line)
    return {"returncode": 0, "log": log, "produced": ["history-stats-latest.json"]}


def load_report(name: str):
    path = REPORTS / name
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data
    return data


def _flatten(d: dict, max_items: int = 10) -> list[str]:
    out: list[str] = []
    for k, v in d.items():
        if k in ("disclaimer", "warning", "multiple_comparison_warning"):
            continue
        if isinstance(v, dict):
            out.append(f"{k}: {{…}}")
        elif isinstance(v, list):
            out.append(f"{k}: [{len(v)} items]")
        else:
            out.append(f"{k}: {v}")
        if len(out) >= max_items:
            break
    return out


def _project_info() -> dict:
    info = {"root": str(ROOT), "db_exists": DB.exists()}
    if not DB.exists():
        return info
    try:
        with sqlite3.connect(str(DB)) as c:
            rows = c.execute(
                "SELECT period,values_json FROM draws ORDER BY CAST(period AS INTEGER)"
            ).fetchall()
        info["draws"] = len(rows)
        if rows:
            info["period_min"] = rows[0][0]
            info["period_max"] = rows[-1][0]
            try:
                f = json.loads(rows[-1][1])
                info["last_draw_date"] = f[-1]
            except Exception:
                pass
    except Exception as exc:
        info["error"] = str(exc)
    return info


def _kpis() -> dict:
    k = {}
    brain = load_report("brain-decision-latest.json")
    if brain:
        k["verdict"] = brain.get("verdict")
        k["selected_model"] = brain.get("selected_for_experiment_only")
    gate = load_report("model-gate-latest.json")
    if gate:
        k["gate_decision"] = gate.get("decision") or gate.get("gate_decision")
    drift = load_report("drift-latest.json")
    if drift:
        k["drift_action"] = drift.get("action")
    leak = load_report("leakage-latest.json")
    if leak:
        k["leakage_status"] = leak.get("status") or leak.get("result")
        if "scanned" in leak:
            k["leakage_scanned"] = leak.get("scanned")
    quality = load_report("quality-latest.json")
    if quality:
        k["quality_rows"] = quality.get("rows") or quality.get("draw_count")
    return k


def _reports_summary() -> list[dict]:
    out = []
    for name in LATEST_REPORTS:
        data = load_report(name)
        if data is None:
            continue
        mtime = (REPORTS / name).stat().st_mtime
        out.append(
            {
                "name": name,
                "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "summary": _flatten(data),
            }
        )
    return out


def list_decisions() -> list[dict]:
    if not DECISIONS.exists():
        return []
    out = []
    for md in sorted(DECISIONS.glob("*.md")):
        if md.name in ("README.md", "TEMPLATE.md"):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        head = text.splitlines()[:40]
        title = md.stem
        status = None
        pid = None
        for line in head:
            if line.startswith("#"):
                title = line.lstrip("# ").strip()
            m = re.search(r"状态[：:]\s*`?([A-Za-z_]+)`?", line)
            if m:
                status = m.group(1)
            m = re.search(r"(EVOLUTION-[\d]+|[\d]{8}-[\w-]+)", line)
            if m and pid is None:
                pid = m.group(1)
        out.append(
            {
                "file": md.name,
                "title": title,
                "status": status or "UNKNOWN",
                "proposal_id": pid or md.stem,
                "mtime": datetime.fromtimestamp(md.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            }
        )
    return out


def git(args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as exc:
        return 1, str(exc)


def git_versions() -> list[dict]:
    versions = []
    rc, out = git(["log", "--pretty=format:%H|%h|%ci|%s", "-n", "12"])
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                h, short, ci, msg = parts
                versions.append({"ref": h, "short": short, "date": ci[:10], "text": msg, "kind": "commit"})
    rc, out = git(["tag"])
    if rc == 0 and out:
        for t in out.splitlines():
            versions.append({"ref": t, "short": t, "date": "", "text": f"tag: {t}", "kind": "tag"})
    return versions


def _timeline() -> list[dict]:
    items = []
    for d in list_decisions():
        items.append({"date": d["mtime"], "type": "decision", "text": f"{d['title']} [{d['status']}]"})
    rc, out = git(["log", "--pretty=format:%ci|%s", "-n", "15"])
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split("|", 1)
            if len(parts) == 2:
                items.append({"date": parts[0][:16].replace("T", " "), "type": "commit", "text": parts[1]})
    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:25]


def rollback(ref: str, confirm: bool = False) -> dict:
    """Restore tracked files to a git ref. Always takes a safety snapshot first.

    This is an L2 operation: callers must pass confirm=True (UI checkbox /
    CLI explicit y/N) before any change is made.
    """
    if not confirm:
        return {"ok": False, "log": ["ABORTED: rollback requires explicit confirmation."]}
    if not ref:
        return {"ok": False, "log": ["ABORTED: no ref provided."]}
    rc, head = git(["rev-parse", "HEAD"])
    if rc == 0 and head.strip() == ref:
        return {"ok": False, "log": ["ABORTED: ref is the current HEAD; nothing to roll back."]}
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    snap = BACKUPS / f"rollback-snapshot-{ts}"
    try:
        snap.mkdir(parents=True, exist_ok=True)
        for sub in ("reports", "docs", "workbench", "predictions", "backups"):
            src = ROOT / sub
            if src.exists():
                shutil.copytree(src, snap / sub, dirs_exist_ok=True)
        shutil.copy(ROOT / "sd3d_history.sqlite3", snap / "sd3d_history.sqlite3") if DB.exists() else None
    except Exception as exc:
        return {"ok": False, "log": [f"Safety snapshot failed, aborting: {exc}"]}
    rc, out = git(["checkout", ref, "--", "."])
    if rc != 0:
        return {"ok": False, "log": [f"git checkout failed:\n{out}", f"Safety snapshot kept at {snap}"]}
    return {"ok": True, "log": [f"Rolled back to {ref}.", f"Safety snapshot at {snap}"]}


def _trim_backtest(data: dict | None) -> dict | None:
    """Drop the heavy per-period prediction list; keep decision-relevant stats."""
    if not data:
        return None
    trimmed = {k: v for k, v in data.items() if k != "frozen_predictions"}
    return trimmed


def collect_state() -> dict:
    return {
        "generated_at": _now(),
        "project": _project_info(),
        "kpis": _kpis(),
        "reports": _reports_summary(),
        "functions": [
            {k: f.get(k) for k in ("id", "title", "risk", "category", "desc", "confirm", "params")}
            for f in FUNCTIONS
        ],
        "decisions": list_decisions(),
        "timeline": _timeline(),
        "versions": git_versions(),
        "backtest": _trim_backtest(load_report("backtest-latest.json")),
        "multi_method": load_report("multi-method-latest.json"),
        "history_stats": load_report("history-stats-latest.json"),
    }
