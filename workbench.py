#!/usr/bin/env python3
"""Workbench CLI: one-click human control surface for the 福彩3D project.

Subcommands:
  list             列出所有可一键操作的功能
  run <id>        同步运行某个功能（输出实时打印）
  backtest         运行严格时间顺序回测
  decisions       列出决策/审计记录
  state           打印当前状态 JSON
  print           打印人类友好的决策摘要（可重定向到文件）
  dashboard [out] 生成静态决策大屏 HTML（默认 dashboard.html，可打印）
  serve [port]    启动交互式决策大屏（默认 8787）
  rollback <ref>  回滚到指定 git 版本（需确认）

本工具不自行修改数据：它编排既有的、受宪章治理的流水线脚本。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from workbench import dashboard, engine, registry  # noqa: E402


def cmd_list(_: argparse.Namespace) -> int:
    print(f"{'ID':<18}{'风险':<5}{'类别':<10}标题")
    print("-" * 60)
    for f in registry.FUNCTIONS:
        print(f"{f['id']:<18}{f['risk']:<5}{f['category']:<10}{f['title']}")
    print(f"\n共 {len(registry.FUNCTIONS)} 个功能。")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    func = registry.by_id(args.id)
    if not func:
        print(f"未知功能 id: {args.id}")
        return 2
    print(f"▶ {func['title']}  [{func['risk']}]")
    res = engine.run_function(args.id, extra_args=list(args.args))
    for line in res["log"]:
        print(line)
    print(f"\n退出码: {res['returncode']}")
    return res["returncode"]


def cmd_multi_method(args: argparse.Namespace) -> int:
    extra = []
    if args.last_n is not None:
        extra += ["--last-n", str(args.last_n)]
    if args.top_k is not None:
        extra += ["--top-k", str(args.top_k)]
    if args.alpha is not None:
        extra += ["--alpha", str(args.alpha)]
    res = engine.run_function("multi_method", extra_args=extra)
    for line in res["log"]:
        print(line)
    return res["returncode"]


def cmd_backtest(_: argparse.Namespace) -> int:
    return cmd_run_type("backtest")


def cmd_run_type(fid: str) -> int:
    res = engine.run_function(fid)
    for line in res["log"]:
        print(line)
    return res["returncode"]


def cmd_decisions(_: argparse.Namespace) -> int:
    ds = engine.list_decisions()
    if not ds:
        print("暂无决策记录。")
        return 0
    for d in ds:
        print(f"[{d['status']:<9}] {d['title']}  ({d['file']}, {d['mtime']})")
    return 0


def cmd_state(_: argparse.Namespace) -> int:
    import json

    print(json.dumps(engine.collect_state(), ensure_ascii=False, indent=2))
    return 0


def cmd_print(_: argparse.Namespace) -> int:
    print(dashboard.print_summary(engine.collect_state()))
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else (ROOT / "dashboard.html")
    html = dashboard.build_html(engine.collect_state(), live=False)
    out.write_text(html, encoding="utf-8")
    print(f"决策大屏已生成: {out.resolve()}")
    print("用浏览器打开即可查看；按 Ctrl/Cmd+P 可打印为 PDF。")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from workbench import serve

    port = args.port or 8787
    try:
        serve.serve(port=port)
    except OSError as exc:
        print(f"无法在端口 {port} 启动服务: {exc}")
        return 1
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    if not args.yes:
        ans = input(f"确认回滚到 {args.ref}？此操作会先生成安全快照再恢复 (y/N): ")
        if ans.strip().lower() != "y":
            print("已取消。")
            return 0
    res = engine.rollback(args.ref, confirm=True)
    for line in res["log"]:
        print(line)
    return 0 if res.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="福彩3D 决策大屏 / 一键控制面")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("list", help="列出所有功能").set_defaults(func=cmd_list)
    pr = sub.add_parser("run", help="运行某个功能（可追加额外参数，如 --top-k 20）")
    pr.add_argument("id", help="功能 id（见 list）")
    pr.add_argument("args", nargs="*", help="额外命令行参数，直接透传给底层脚本")
    pr.set_defaults(func=cmd_run)
    sub.add_parser("backtest", help="运行回测").set_defaults(func=cmd_backtest)
    pm = sub.add_parser("multi_method", help="多方法预测对比报告（底层多种预测方式共存）")
    pm.add_argument("--last-n", type=int, default=12, help="回看期数")
    pm.add_argument("--top-k", type=int, default=10, help="候选数")
    pm.add_argument("--alpha", type=float, default=0.1, help="分布平滑系数")
    pm.set_defaults(func=cmd_multi_method)
    sub.add_parser("decisions", help="列出决策记录").set_defaults(func=cmd_decisions)
    sub.add_parser("state", help="打印状态 JSON").set_defaults(func=cmd_state)
    sub.add_parser("print", help="打印决策摘要").set_defaults(func=cmd_print)
    pd = sub.add_parser("dashboard", help="生成静态大屏 HTML")
    pd.add_argument("out", nargs="?", help="输出路径（默认 dashboard.html）")
    pd.set_defaults(func=cmd_dashboard)
    ps = sub.add_parser("serve", help="启动交互式大屏")
    ps.add_argument("port", nargs="?", type=int, help="端口（默认 8787）")
    ps.set_defaults(func=cmd_serve)
    prb = sub.add_parser("rollback", help="回滚到 git 版本")
    prb.add_argument("ref", help="git ref（commit hash / tag）")
    prb.add_argument("--yes", action="store_true", help="跳过确认")
    prb.set_defaults(func=cmd_rollback)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
