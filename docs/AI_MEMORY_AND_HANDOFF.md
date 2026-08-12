# AI/Agent 记忆与交接规范

## 接手检查清单

- [ ] 阅读根目录 `PROJECT_CHARTER.md` 及其版本。
- [ ] 确认当前 Git/文件版本和工作区是否有未提交改动。
- [ ] 读取 SQLite 期数、最小/最大期号、运行状态和 JSONL 审计日志最后哈希。
- [ ] 检查最近数据质量报告、失败运行和未决修订案。
- [ ] 明确本次工作是只读、普通实现、高风险变更还是宪章修订。
- [ ] 写出备份位置、回滚路径和验证命令。

## 交接记录最小格式

```text
handoff_id:
charter_version:
agent:
date:
scope:
read_files:
current_data_range:
current_db_hash:
current_tx_tail_hash:
uncommitted_changes:
known_risks:
next_safe_action:
```

## 禁止的“记忆”

以下内容不能只写在聊天上下文中：数据修正原因、接口变化、模型结论、基线变化、投票结果、回滚方案和任何“以后都这样做”的规则。它们必须落到版本化文档、运行清单、审计报告或 `.tx` 记录中。

## 结论措辞

Agent 应使用“在该时间窗口和该基线下未观察到稳定优势”“该规则筛掉了部分历史样本”“该结果可能由随机波动解释”等表述，避免使用“保证”“必出”“稳定预测”“确定排除”等措辞。
