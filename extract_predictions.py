#!/usr/bin/env python3
"""提取福彩3D项目的「冻结预测结果」。

读取 predictions/frozen-*.json（预测产物，不含 *-comparison 对照文件），
可选关联 sqlite `draws` 表追加实际开奖与命中情况，导出为干净的 CSV/JSON。

只读：绝不修改任何源 JSON、sqlite 库或其它数据文件，只新写一个提取报告。

用法：
  python extract_predictions.py                      # 导出 CSV -> predictions/extracted_predictions.csv
  python extract_predictions.py --json out.json       # 同时/改为导出 JSON
  python extract_predictions.py --no-outcome          # 不关联实际开奖（纯预测侧）
  python extract_predictions.py --db sd3d_history.sqlite3 --top 20
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path


def load_draws(db_path: Path) -> dict[str, str]:
    """period -> 3-digit actual number. 读取失败返回空 dict。"""
    if not db_path.exists():
        return {}
    try:
        with sqlite3.connect(db_path) as c:
            rows = c.execute("SELECT period, values_json FROM draws").fetchall()
    except sqlite3.Error:
        return {}
    out = {}
    for period, payload in rows:
        try:
            fields = json.loads(payload)
            number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
            if len(number) == 3:
                out[str(period)] = number
        except Exception:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="提取福彩3D冻结预测结果（只读）")
    ap.add_argument("--root", type=Path, default=Path(__file__).parent, help="项目根目录")
    ap.add_argument("--db", type=Path, default=None, help="sqlite 历史库（默认 <root>/sd3d_history.sqlite3）")
    ap.add_argument("--out", type=Path, default=None, help="CSV 输出路径")
    ap.add_argument("--json", type=Path, default=None, help="额外导出 JSON 到该路径")
    ap.add_argument("--no-outcome", action="store_true", help="不关联实际开奖")
    ap.add_argument("--top", type=int, default=0, help="仅保留最近 N 期（0=全部）")
    args = ap.parse_args()

    root = args.root.resolve()
    pred_dir = root / "predictions"
    db_path = args.db or (root / "sd3d_history.sqlite3")
    out_csv = args.out or (pred_dir / "extracted_predictions.csv")

    if not pred_dir.exists():
        sys.stderr.write(f"未找到预测目录：{pred_dir}\n")
        return 1

    draws = {} if args.no_outcome else load_draws(db_path)
    if not args.no_outcome and not draws:
        sys.stderr.write(f"[warn] 未加载实际开奖（db={db_path}）；仅输出预测侧。\n")

    rows = []
    for path in sorted(pred_dir.glob("frozen-*.json")):
        if "comparison" in path.name:
            continue  # 跳过对照产物，只处理原始预测
        try:
            art = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if art.get("kind") != "frozen_prediction":
            continue
        target = str(art.get("target_period", ""))
        candidates = art.get("candidates", []) or []
        actual = draws.get(target)
        exact = (actual in candidates) if (actual is not None and candidates) else None
        max_hits = None
        if actual is not None and candidates:
            max_hits = max(
                (sum(a == b for a, b in zip(actual, cand)) for cand in candidates),
                default=0,
            )
        rows.append({
            "target_period": target,
            "created_at": art.get("created_at", ""),
            "model": art.get("model", ""),
            "training_cutoff": str(art.get("training_cutoff_period", "")),
            "top_candidate": candidates[0] if candidates else "",
            "candidate_count": len(candidates),
            "all_candidates": " ".join(candidates),
            "actual": actual or "",
            "exact_hit": ("" if exact is None else ("YES" if exact else "no")),
            "max_position_hits": ("" if max_hits is None else max_hits),
        })

    if args.top and args.top > 0:
        rows = rows[-args.top:]

    if not rows:
        sys.stderr.write("没有找到可提取的冻结预测（predictions/frozen-*.json）。\n")
        return 1

    # 写 CSV
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[csv]  {len(rows)} 期预测 -> {out_csv}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[json] -> {args.json}")

    # 控制台摘要
    hits = sum(1 for r in rows if r["exact_hit"] == "YES")
    completed = sum(1 for r in rows if r["actual"])
    print(f"\n共提取 {len(rows)} 期预测"
          + (f"，其中 {completed} 期已有实际开奖、精确命中 {hits} 期。" if not args.no_outcome else "（未关联开奖）。"))
    print("最近 5 期预览：")
    for r in rows[-5:]:
        line = f"  期{r['target_period']}  预测Top={r['top_candidate']}  共{r['candidate_count']}个"
        if r["actual"]:
            line += f"  实际={r['actual']}  命中={r['exact_hit']}"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
