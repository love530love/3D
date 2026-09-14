"""checkpoint.py — 安全探索的版本管理骨架（状态级快照/还原 + git 标签）。

目的：让离线/自动探索在"失败 / 崩溃 / 走错方向"时可以一键还原并重试，
彻底消除"探索失败却无法还原"的风险。

与 engine.rollback 的分工：
  * engine.rollback  —— 还原【代码 / 已跟踪文件】到某个 git ref（版本管理）。
  * checkpoint       —— 还原【运行时状态 / 报告 / 账本】到某次探索前的快照点（探索安全网）。
两者互补：checkpoint 在每次探索批次前自动打点，并把当时的代码版本记成 git tag，
restore 时既还原状态目录，也可选择性 checkout 回当时代码版本。

使用：
  python -m workbench.checkpoint snapshot --label pre-batch-3
  python -m workbench.checkpoint list
  python -m workbench.checkpoint restore <id> --confirm [--code]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
SNAP_DIR = ROOT / "snapshots"

# 纳入快照的状态来源（相对 ROOT）。reports/ 是核心；顶层的引擎累积状态也一并保全。
TOP_STATE_FILES = ["evolution-engine-state.json"]


def _git(args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as exc:  # pragma: no cover
        return 1, str(exc)


def _head_commit() -> str:
    rc, out = _git(["rev-parse", "HEAD"])
    return out.strip() if rc == 0 else ""


def _index_path() -> Path:
    return SNAP_DIR / "index.json"


def _append_index(m: dict) -> None:
    p = _index_path()
    arr = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    arr.append({
        "id": m["id"], "label": m["label"], "created_at": m["created_at"],
        "git_tag": m.get("git_tag"), "fitness": m.get("fitness"),
        "saved": m.get("saved", []),
    })
    p.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")


def _rel_walk(root: Path) -> list[str]:
    if not root.exists():
        return []
    return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]


def snapshot(label: str, notes: str = "", fitness: float | None = None) -> dict:
    """在时间前向探索批次前打点。返回 manifest。

    关键改进：记录每个已保全目标的【文件清单】，使 restore 可做到靶向还原
    （只覆盖快照内文件、只删除"快照之后新增"的文件），而非整目录 rmtree——
    后者会误删其它模块的报告，且在某些受限环境被安全护栏拦截。
    """
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    sid = f"{ts}-{label}"
    dest = SNAP_DIR / sid
    dest.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    saved_files: dict[str, list[str]] = {}

    if REPORTS.exists():
        shutil.copytree(REPORTS, dest / "reports", dirs_exist_ok=True)
        saved.append("reports")
        saved_files["reports"] = _rel_walk(dest / "reports")
    for f in TOP_STATE_FILES:
        p = ROOT / f
        if p.exists():
            shutil.copy(p, dest / f)
            saved.append(f)
            saved_files[f] = [f]

    commit = _head_commit()
    tag = f"ckpt-{sid}"
    rc, _ = _git(["tag", tag])
    tag_ok = (rc == 0)

    manifest = {
        "id": sid, "label": label, "notes": notes,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": commit, "git_tag": tag if tag_ok else None,
        "fitness": fitness, "saved": saved, "saved_files": saved_files,
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_index(manifest)
    return manifest


def list_snapshots() -> list[dict]:
    p = _index_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def restore(sid: str, confirm: bool = False, checkout_code: bool = False) -> dict:
    """靶向还原到某快照点。必须显式 confirm。可选同时 checkout 当时代码版本。

    安全性：
      * 仅覆盖快照内记录的文件（不会破坏快照之外的其它模块报告）。
      * 仅删除"快照之后新增"的文件（靶向 unlink，不做整目录 rmtree）。
      * 还原前先把当前 reports/ 备份到 _pre_restore_<ts>，避免 half-write 丢失。
    """
    if not confirm:
        return {"ok": False, "log": ["ABORTED: restore requires explicit --confirm."]}
    dest = SNAP_DIR / sid
    man = dest / "manifest.json"
    if not man.exists():
        return {"ok": False, "log": [f"snapshot {sid} not found"]}
    m = json.loads(man.read_text(encoding="utf-8"))
    log: list[str] = []
    saved_files: dict[str, list[str]] = m.get("saved_files", {})

    if (dest / "reports").exists():
        backup = SNAP_DIR / f"_pre_restore_{datetime.now():%Y%m%d%H%M%S}"
        if REPORTS.exists():
            shutil.copytree(REPORTS, backup, dirs_exist_ok=True)
            log.append(f"backed up current reports/ to {backup.name}")
        snap_reports = set(saved_files.get("reports", []))
        # 1) 覆盖快照内文件
        for rel in snap_reports:
            src = dest / "reports" / rel
            dst = REPORTS / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
        # 2) 删除快照之后新增的文件（靶向，不 rmtree 整目录）
        removed = 0
        if REPORTS.exists():
            for cur in REPORTS.rglob("*"):
                if cur.is_file():
                    rel = str(cur.relative_to(REPORTS))
                    if rel not in snap_reports:
                        try:
                            cur.unlink()
                            removed += 1
                        except Exception:
                            pass
        log.append(f"restored reports/ (overwrote {len(snap_reports)} files, removed {removed} post-snapshot files)")
    for f in m.get("saved", []):
        if f != "reports" and (dest / f).exists():
            shutil.copy(dest / f, ROOT / f)
            log.append(f"restored {f}")
    log.append(f"restored state from {sid}")

    if checkout_code and m.get("git_tag"):
        rc, out = _git(["checkout", m["git_tag"], "--", "."])
        log.append(f"code checkout {m['git_tag']}: {'OK' if rc == 0 else out}")

    return {"ok": True, "log": log, "manifest": m}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="安全探索快照 / 还原")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="探索前打点")
    s.add_argument("--label", required=True)
    s.add_argument("--notes", default="")
    s.add_argument("--fitness", type=float, default=None)

    l = sub.add_parser("list", help="列出快照")
    r = sub.add_parser("restore", help="还原快照")
    r.add_argument("id")
    r.add_argument("--confirm", action="store_true")
    r.add_argument("--code", action="store_true", help="同时 checkout 当时代码版本")

    args = ap.parse_args()
    if args.cmd == "snapshot":
        m = snapshot(args.label, args.notes, args.fitness)
        print(json.dumps(m, ensure_ascii=False, indent=2))
    elif args.cmd == "list":
        print(json.dumps(list_snapshots(), ensure_ascii=False, indent=2))
    elif args.cmd == "restore":
        print(json.dumps(restore(args.id, args.confirm, args.code), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
