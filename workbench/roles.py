"""roles.py — 自描述角色注册表（任意 AI / 离线运行均可发现与扩展）.

角色表是 项目内部"进化能力"的单一真相源：
  * 任意 AI 接入第一件事 = list()/describe() 读取契约，无需特定对话记忆。
  * 新增角色 = register()，进入 proposed 态 -> 裁判团+守门员法定人数审批 -> active。
  * 不变量：任何声明写引擎状态的角色 MUST 声明 required_gate in {interventions, referee, none}，
    禁止 "direct"（否则守门员自动拒）。能力用枚举，非自由文本。

这与 engine.rollback / checkpoint 共同构成"版本管理 + 探索安全网"底座。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG_PATH = Path(__file__).resolve().parent / "roles.json"

# 允许的能力枚举（新枚举需宪章修订 L3，防权限膨胀）
ALLOWED_CAPS = {
    "read_state", "propose", "judge", "archive", "orchestrate",
    "direct", "override_via_gate",
}
# 合法的写路径闸门（禁止 direct）
ALLOWED_GATES = {"interventions", "referee", "none"}
# 审批法定人数所需的"人类式/深度"守门角色
APPROVER_ROLES = {"referee", "gatekeeper", "human_principal"}


def load_registry() -> list[dict]:
    if not REG_PATH.exists():
        return []
    return json.loads(REG_PATH.read_text(encoding="utf-8"))


def save_registry(roles: list[dict]) -> None:
    REG_PATH.write_text(json.dumps(roles, ensure_ascii=False, indent=2), encoding="utf-8")


def active_roles() -> list[dict]:
    return [r for r in load_registry() if r.get("status") == "active"]


def role_by_id(rid: str) -> dict | None:
    for r in load_registry():
        if r["id"] == rid:
            return r
    return None


def list_roles(verbose: bool = False) -> list[dict]:
    roles = load_registry()
    if not verbose:
        return [{"id": r["id"], "name_cn": r.get("name_cn"), "intelligence": r.get("intelligence"),
                 "status": r.get("status"), "required_gate": r.get("required_gate")} for r in roles]
    return roles


def describe(rid: str) -> dict | None:
    return role_by_id(rid)


def _validate_spec(spec: dict) -> list[str]:
    errs: list[str] = []
    if "id" not in spec or "name_cn" not in spec:
        errs.append("spec 必须含 id 与 name_cn")
    caps = set(spec.get("capabilities", []))
    unknown = caps - ALLOWED_CAPS
    if unknown:
        errs.append(f"未知能力枚举: {sorted(unknown)}")
    gate = spec.get("required_gate", "interventions")
    if gate not in ALLOWED_GATES:
        errs.append(f"required_gate 必须是 {sorted(ALLOWED_GATES)}，收到 {gate}")
    if "propose" in caps or "override_via_gate" in caps or "direct" in caps:
        # 任何能'写'的角色必须经闸门；direct 一律拒绝
        if gate == "direct":
            errs.append("守门员拒绝：写路径不得为 direct，必须经 interventions/referee")
    if spec.get("kind") not in ("derived", "inherent"):
        errs.append("kind 必须是 derived 或 inherent")
    return errs


def register(spec_path: str, approvers: list[str] | None = None, notes: str = "") -> dict:
    """注册新角色：校验 -> proposed -> 法定人数审批 -> active/rejected。

    不修改现有角色；新角色追加到注册表。审批人须 >=2 且取自 APPROVER_ROLES。
    """
    p = Path(spec_path)
    if not p.exists():
        return {"ok": False, "log": [f"spec 不存在: {spec_path}"]}
    spec = json.loads(p.read_text(encoding="utf-8"))

    errs = _validate_spec(spec)
    if errs:
        return {"ok": False, "log": ["校验失败:"] + errs}

    approvers = set(approvers or [])
    valid_appr = approvers & APPROVER_ROLES
    if len(valid_appr) < 2:
        # 进入 proposed，等后续审批，不激活
        spec["status"] = "proposed"
        spec.setdefault("intelligence", ["ai"])
        spec.setdefault("isolation", "isolated")
        spec["notes"] = notes
        roles = load_registry()
        if any(r["id"] == spec["id"] for r in roles):
            return {"ok": False, "log": [f"角色 id 已存在: {spec['id']}"]}
        roles.append(spec)
        save_registry(roles)
        return {"ok": True, "activated": False,
                "log": [f"角色 {spec['id']} 进入 proposed 态（审批人不足 {sorted(valid_appr)}，需 >=2 来自 {sorted(APPROVER_ROLES)}）",
                        "后续可用 register --approve 补签后激活"]}

    spec["status"] = "active"
    spec.setdefault("intelligence", ["ai"])
    spec.setdefault("isolation", "isolated")
    spec["approved_by"] = sorted(valid_appr)
    spec["notes"] = notes
    roles = load_registry()
    if any(r["id"] == spec["id"] for r in roles):
        return {"ok": False, "log": [f"角色 id 已存在: {spec['id']}"]}
    roles.append(spec)
    save_registry(roles)
    return {"ok": True, "activated": True,
            "log": [f"角色 {spec['id']} 已激活（审批人 {sorted(valid_appr)}）"]}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="自描述角色注册表")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出角色（契约摘要）")
    d = sub.add_parser("describe", help="查看某角色完整契约")
    d.add_argument("id")
    r = sub.add_parser("register", help="注册新角色（-> proposed/active）")
    r.add_argument("--spec", required=True)
    r.add_argument("--approver", action="append", default=[], help="审批人角色 id（需 >=2）")
    r.add_argument("--notes", default="")
    e = sub.add_parser("exec", help="驱动某角色执行器（gatekeeper/replicator/bias_auditor/ideator/archivist/orchestrator）")
    e.add_argument("id", help="角色 id")
    e.add_argument("--db", default=str(ROOT / "sd3d_history.sqlite3"))
    e.add_argument("--jsonl", default=None, help="bias_auditor 的干预账本路径")

    args = ap.parse_args()
    if args.cmd == "list":
        print(json.dumps(list_roles(), ensure_ascii=False, indent=2))
    elif args.cmd == "describe":
        print(json.dumps(describe(args.id), ensure_ascii=False, indent=2))
    elif args.cmd == "register":
        print(json.dumps(register(args.spec, args.approver, args.notes), ensure_ascii=False, indent=2))
    elif args.cmd == "exec":
        from workbench import roles_exec
        result = roles_exec.run_role(args.id, db=args.db, jsonl_path=args.jsonl)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
