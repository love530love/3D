# 福彩3D统计学习与随机性实验平台

这是一个证据优先、可恢复、可审计的福彩3D数据工程与统计学习项目。项目目标是学习采集、数据质量、概率、时间序列、机器学习评估和科学复现，同时用严格回测检验“彩票是否存在稳定可预测优势”的说法。

> 重要：任何候选、排名或命中都不构成投注建议，也不能证明下一期可预测。所有模型必须和均匀随机基线比较。

## 快速开始

使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe run_update_cycle.py
.\.venv\Scripts\python.exe run_pipeline.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

如果只想查看已有数据，不访问网络：

```powershell
.\.venv\Scripts\python.exe run_update_cycle.py --no-fetch --skip-pipeline
```

## 当前能力

```text
福彩3D iframe 采集
  -> 增量去重 SQLite
  -> JSONL 哈希链审计
  -> 原始 HTML 快照
  -> 数据质量门禁
  -> 随机性诊断
  -> challenger 统一回测
  -> Brier / Log Loss / 校准
  -> Bootstrap 区间比较
  -> 冻结预测与实际结果盲评
  -> 教学报告
  -> 综合证据大脑
```

主要入口：

- `fetch_sd3d.py`：安全增量采集。
- `validate_sd3d.py`：数据库、审计链和来源快照门禁。
- `run_pipeline.py`：只读分析流水线。
- `run_update_cycle.py`：日常更新、旧预测盲评和新预测冻结。
- `replay_snapshot.py`：离线重放原始响应。
- `evidence_brain.py`：汇总所有证据并生成受治理约束的综合判断。

## 数据与 Git 边界

Git 私人仓库保存代码、文档、测试、治理规则和配置。SQLite、JSONL、原始快照、CSV 和报告是运行产物，默认被 `.gitignore` 排除；它们通过 SHA-256 和备份清单管理。

## 治理入口

开始任何修改前阅读：

1. `AGENTS.md`
2. `PROJECT_CHARTER.md`
3. `docs/AI_MEMORY_AND_HANDOFF.md`
4. `docs/DATA_PERSISTENCE.md`

预测建模专项还必须阅读 `docs/PREDICTION_MODELING_GOVERNANCE.md`。
新增模型使用 `docs/MODEL_PROPOSAL_TEMPLATE.md` 发起评审。
中枢模型选型见 `docs/CENTRAL_BRAIN_MODEL_SELECTION.md`；语言模型默认只作为只读解释层。

涉及数据契约、存储、模型评估定义或宪章的变更，必须经过规定的 subagent 专家审计和投票。

## 结果解释

单期命中、短期频率偏差、显著 p 值或某个模型暂时领先，都可能由随机波动、探索性多重比较或过拟合造成。可信结论必须同时通过时间外推、基线比较、概率评分、校准、Bootstrap 和盲评。
