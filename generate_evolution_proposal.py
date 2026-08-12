"""Create a reviewable evolution proposal from current evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    p = argparse.ArgumentParser(description="根据综合证据生成受审计的模型进化提案草案")
    base = Path(__file__).parent
    p.add_argument("--reports", type=Path, default=base / "reports")
    p.add_argument("--out", type=Path, default=base / "docs" / "decisions" / "EVOLUTION-DRAFT.md")
    args = p.parse_args()
    brain = read(args.reports / "brain-decision-latest.json")
    drift = read(args.reports / "drift-latest.json")
    outcomes = read(args.reports / "outcomes-latest.json")
    proposal_id = "EVOLUTION-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    text = f"""# 模型进化提案：{proposal_id}

状态：`DRAFT`（禁止自动实施）

生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}

## 触发证据

- 综合判断：`{brain.get('verdict', 'UNKNOWN')}`
- 当前实验模型：`{brain.get('selected_for_experiment_only', 'UNKNOWN')}`
- 漂移动作：`{drift.get('action', 'UNKNOWN')}`
- 盲评完成数：`{outcomes.get('completed', 'UNKNOWN')}`
- 盲评待完成数：`{outcomes.get('pending', 'UNKNOWN')}`

## 提案意图

仅申请对下一版 challenger 进行离线研究，不申请替换正式基线，不申请修改历史数据，不申请改变冻结预测。

## 必须完成的审计

- [ ] 数据溯源专家确认没有新增未来信息或快照缺失。
- [ ] 统计专家确认时间滚动回测、随机基线和多重比较方案。
- [ ] 工程专家确认依赖、资源和可复现运行清单。
- [ ] 存储专家确认失败可回滚且不修改 SQLite/JSONL 历史。
- [ ] 教学与伦理专家确认结论不会包装成稳定获利或确定预测。

## 验收门槛

- [ ] 至少一个完整时间外推窗口。
- [ ] 同时报告命中、Brier、Log Loss、校准和 Bootstrap 区间。
- [ ] 提供失败案例和与均匀基线的差异。
- [ ] 区间跨 0 或无稳定优势时，保持 challenger 身份。

## 决定

专家报告位置：  
投票结果：  
生效版本：  
回滚方案：
"""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"Evolution proposal draft: {args.out.resolve()}")


if __name__ == "__main__":
    main()
