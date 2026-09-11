# 福彩3D统计学习与随机性实验平台

这是一个**证据优先、可恢复、可审计**的福彩3D数据工程与统计学习项目。项目目标是学习采集、数据质量、概率、时间序列、机器学习评估和科学复现，同时用严格回测检验“彩票是否存在稳定可预测优势”这种说法。

> ⚠️ **重要**：本项目任何候选、排名或命中都**不构成投注建议**，也不能证明下一期可以预测。所有模型都必须和“均匀随机基线”对比。彩票开奖按随机过程处理。

---

## 一、这个项目能让你学到什么

- **数据工程**：如何用 SQLite + JSONL 哈希链 + 原始 HTML 快照，把“网页抓取”做成可审计、可回放的证据链。
- **统计与随机性**：χ² 拟合优度、lag-1 自相关、置换检验、Bootstrap 置信区间、Brier / Log Loss、校准曲线。
- **机器学习评估纪律**：时间序列只能“按期号向前训练”、预测必须先冻结再读结果（盲评）、任何复杂方法都要和透明基线比较。
- **治理与复现**：宪章（Charter）约束数据主权、修改分级（L0–L3）、专家审计投票、紧急冻结。

---

## 二、环境准备（新手必读）

项目**只依赖 Python 标准库**（`.venv` 为 Python 3.14.0，`requirements.txt` 为空，无需 `pip install`）。

```powershell
# 进入项目根目录
cd F:\PythonProjects1\3D

# 如果还没有虚拟环境（.venv 已被 git 忽略，不会随仓库分发），自己建一个：
python -m venv .venv
# 因为不需要第三方包，建好即可，无需安装依赖

# 之后所有命令都用这个解释器运行（下面统一记作 `.venv`）：
.\.venv\Scripts\python.exe <脚本名>.py
```

> 提示：仓库里已自带 `.venv`，直接用它即可。若重装，标准库即可跑通全部脚本。

---

## 三、两条主命令：每天怎么跑

绝大多数时候你只需要这两条命令：

```powershell
# ① 日常端到端更新（推荐每天跑一次）
.\.venv\Scripts\python.exe run_update_cycle.py

# ② 只读分析流水线（不联网、不冻结新预测，只看已有数据）
.\.venv\Scripts\python.exe run_pipeline.py

# ③ 跑测试，确认代码没坏
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- `run_update_cycle.py` **会**做完整流程，并在最后**冻结下一期的统计候选预测**（生成新的 `predictions/frozen-*.json`）。
- `run_pipeline.py` **只做分析、生成报告**，不会采集新数据、也不会生成预测。
- 只想离线演练、不碰网络也不跑分析：

```powershell
.\.venv\Scripts\python.exe run_update_cycle.py --no-fetch --skip-pipeline
```

---

## 四、端到端数据流（看这张图就懂整体）

```text
福彩3D 官网 iframe / 历史接口
        │  fetch_sd3d.py（安全增量采集，去重）
        ▼
  sd3d_history.sqlite3  ← 权威存储（draws 表，按期号去重）
  sd3d_history.jsonl     ← 追加式哈希链审计日志
  raw_snapshots/*.html   ← 原始网页快照（证据资产）
        │  validate_sd3d.py（数据库 + 审计链 + 快照哈希门禁）
        ▼
  reports/quality-latest.json
        │  run_pipeline.py（只读分析流水线，见下表）
        ▼
  reports/*.json  ← 随机性/概率/回测/漂移/模型门禁/证据大脑 等
        │  record_outcomes.py（把已开奖的旧预测写入盲评档案）
        ▼
  sqlite: prediction_outcomes 表 + reports/outcomes-latest.json
        │  predict_sd3d.py（冻结下一期候选，先于实际结果生成）
        ▼
  predictions/frozen-<target>-<run_id>.json   ← “先冻结，后看结果”
```

**冻结（freeze）先于评估（evaluate）是铁律**：`predict_sd3d.py` 在开奖前生成候选；等该期开奖进入 `draws` 表后，下轮 `run_update_cycle.py` 会调用 `compare_prediction.py` 把实际结果附到 `-comparison.json` 里做盲评。这样永远不会因为“偷看未来”而虚报命中。

---

## 五、命令速查表：作用 / 效果 / 产出

> 约定：`<root>` = 项目根目录 `F:\PythonProjects1\3D`；所有脚本默认参数都已指向正确路径，通常无需手写参数。

### 5.1 日常入口（你最常敲的命令）

| 命令 | 作用 | 主要效果 | 关键产出 | 失败时 |
|------|------|----------|----------|--------|
| `run_update_cycle.py` | 日常端到端更新（盲评旧预测 → 采集 → 校验 → 分析 → 记录 → 冻结新预测） | 跑完整治理链路；最后打印 `Update cycle PASS` 并生成下一期冻结预测 | 新 `predictions/frozen-*.json`；刷新 `reports/*` | 任一步非零退出即停止（如泄漏扫描 FAIL） |
| `run_pipeline.py` | 只读分析流水线（不联网、不预测） | 按固定顺序跑 15 个子步骤（含测试） | 刷新全部 `reports/*.json`；末行打印 `[pipeline] PASS` | 打印 `[pipeline] STOP: <脚本> exit=N` |
| `extract_predictions.py` | 只读导出冻结预测 + 命中情况到表格 | 把 `predictions/frozen-*.json` 关联 `draws` 表，算出命中 | `predictions/extracted_predictions.csv`（另有 `--json` 输出） | 无冻结文件时打印提示并退出 |

### 5.2 采集与校验

| 命令 | 作用 | 主要效果 | 关键产出 |
|------|------|----------|----------|
| `fetch_sd3d.py` | 安全增量采集最新开奖 | 只新增“库里没有的期号”，不覆盖历史；已是最新时打印 `No new draw rows` | `draws` 表（SQLite）、`sd3d_history.jsonl`（审计行）、`raw_snapshots/<sha256>.html` |
| `validate_sd3d.py` | 数据质量门禁 | 校验期号唯一可排序、开奖号三位数字、原始快照哈希一致、JSONL 哈希链连续 | `reports/quality-latest.json`（status: PASS/FAIL） |
| `replay_snapshot.py` | 离线重放原始 HTML 响应 | 用本地 `raw_snapshots/*.html` 重跑解析，无需联网 | 复现抓取时的解析结果 |

### 5.3 预测冻结与盲评

| 命令 | 作用 | 主要效果 | 关键产出 |
|------|------|----------|----------|
| `predict_sd3d.py` | **冻结**下一期候选（开奖前运行） | 用“位置频率基线”生成 top-k 候选，**不含任何实际结果** | `predictions/frozen-<target>-<run_id>.json` |
| `compare_prediction.py` | 对已有冻结预测做盲评对照 | 读取该期实际开奖，计算精确命中 / 位置命中 | `predictions/frozen-<target>-<run_id>-comparison.json` |
| `record_outcomes.py` | 长期盲评档案入库 | 把已开奖的预测写入 `prediction_outcomes` 表（已开奖=completed，未开奖=pending） | SQLite `prediction_outcomes` 表 + `reports/outcomes-latest.json` |

### 5.4 分析子步骤（由 `run_pipeline.py` 自动调用）

这些脚本一般不用手动跑，了解它们“产出什么文件”即可读懂 `reports/` 目录：

| 命令 | 产出文件 | 说明 |
|------|----------|------|
| `analyze_sd3d.py` | `analysis-<id>.json` / `manifest-<id>.json` | 基础频率与 Monte Carlo 探针 |
| `diagnose_sd3d.py` | `randomness-latest.json` | 随机性诊断（χ²、lag-1 相关等） |
| `evaluate_models.py` | （并入模型报告） | 全部 challenger 统一回测 |
| `model_screening.py` | `models-latest.json` | 透明基线/challenger 描述性证据 |
| `probability_metrics.py` | `probability-latest.json` | Brier / Log Loss / 校准 |
| `drift_sd3d.py` | `drift-latest.json` | 近期 vs 历史分布漂移 |
| `compare_models_stats.py` | `model-comparison-latest.json` | 与均匀随机基线的 Bootstrap 比较 |
| `model_gate.py` | `model-gate-latest.json` | 模型晋级门槛（`BASELINE_REQUIRED` / `CHALLENGER_REVIEW`） |
| `analyze_outcomes.py` | `outcomes-analysis-latest.json` | 已记录盲评的聚合统计 |
| `scan_leakage.py` | `leakage-latest.json` | 扫描冻结产物是否泄漏未来/结果 |
| `evidence_brain.py` | `brain-decision-latest.json` | 汇总全部证据的综合判断（verdict） |
| `brain_contract.py` | （契约校验） | 确认大脑不自动改代码/删数据 |
| `generate_evolution_proposal.py` | （演化提案草稿） | 基于证据大脑生成后续提案 |
| `build_teaching_report.py` | 教学报告 | 汇总成可读报告 |

---

## 六、数据存放与 Git 边界

**权威存储（不要手改）**
- `sd3d_history.sqlite3`：可查询权威库，`draws` 表为开奖主表（WAL 模式，文件旁有 `-wal`/`-shm` 临时文件）。
- `sd3d_history.jsonl`：追加式审计日志，每行一个事件，靠 `previous_hash` → `event_hash` 形成哈希链，不可篡改。
- `raw_snapshots/*.html`：原始网页快照，是证据资产。

**可重建产物（默认被 `.gitignore` 排除）**
- `reports/*`（分析 JSON）、`predictions/*`（冻结与对照）、`sd3d_*.csv`、`outball.csv` 等 CSV、`raw_snapshots/`。
- 这些都能通过重跑命令再生；CSV 只是导出，不是数据源。

**Git 私人仓库保存**：代码、文档、测试、治理规则、配置。数据/快照/报告不进版本库，改用 SHA-256 校验与备份清单管理（见 `docs/DATA_PERSISTENCE.md`）。

---

## 七、怎么读懂结果：有没有“稳定规律”？

跑完 `run_update_cycle.py` 或 `run_pipeline.py` 后，看这几个文件的结论：

1. **`reports/brain-decision-latest.json` → `verdict`**
   - `NO_STABLE_PREDICTIVE_EDGE_OBSERVED`：当前证据**未显示**稳定超过随机基线的优势（这是本项目的常态结论）。
   - `CHALLENGER_REVIEW_REQUIRED`：历史上有需要专家复核的差异，但仍**不足以证明可预测**。
   - `FROZEN_DATA_QUALITY_FAILURE`：质量门禁失败，先修数据，不发布任何结论。
2. **`reports/model-gate-latest.json` → `status`**
   - `BASELINE_REQUIRED`：任何模型晋级都须先走专家审计 + 正式投票。本项目当前即此状态。
   - `CHALLENGER_REVIEW`：有候选进入复核门槛（不代表已晋升）。
3. **`reports/leakage-latest.json` → `status`**
   - `PASS` 表示冻结产物没有泄漏时序/结果；`FAIL` 会直接让流水线停止（不会带着泄漏继续发布）。
4. **`reports/quality-latest.json` → `status`**
   - `PASS`/`FAIL` 数据质量门禁。

> 📌 **怎么判断“有没有收敛规律”**：单期命中、短期频率偏差、某个 p 值显著、某模型暂时领先，都可能来自随机波动、多重比较或拟合。**可信结论必须同时通过**：时间外推、基线比较、概率评分、校准、Bootstrap、盲评。本项目经严格检验后的既定结论为：**未发现稳定可预测优势（NO_STABLE_PREDICTIVE_EDGE_OBSERVED），模型门禁维持 BASELINE_REQUIRED。**

---

## 八、治理红线（新手千万别踩）

1. **预测必须先冻结，后读结果**：`predict_sd3d.py` 必须在开奖前跑；读实际结果只在 `compare_prediction.py` 的盲评阶段发生。
2. **时间序列只能向前训练**：绝不能把未来开奖泄漏进过去特征或模型选择。
3. **任何复杂方法都要和均匀随机基线比**：不能因为模型“名字先进”就替换透明基线。
4. **不得把随机波动说成预测能力或投注建议**：所有产出的 `disclaimer` 字段都强调这一点。
5. **运行失败不得减少已有数据**：DB/日志损坏时自动进入冻结态，只复制证据、不继续改写。
6. **改代码前的阅读清单**（见下一节）；涉及数据契约/宪章/评估定义的修改必须走专家审计与投票（L2/L3），不是普通实现（L1）。

---

## 九、改代码前必读（治理入口）

开始任何修改前，至少阅读：

1. `AGENTS.md`
2. `PROJECT_CHARTER.md`（项目宪章，高于普通任务描述）
3. `docs/AI_MEMORY_AND_HANDOFF.md`（接手与交接格式）
4. `docs/DATA_PERSISTENCE.md`（数据契约与边界）
5. `docs/PROJECT_ARCHITECTURE.md`（分层架构）

预测建模专项还必须读 `docs/PREDICTION_MODELING_GOVERNANCE.md`；新增模型用 `docs/MODEL_PROPOSAL_TEMPLATE.md` 发起评审；中枢模型选型见 `docs/CENTRAL_BRAIN_MODEL_SELECTION.md`（语言模型默认只作为只读解释层）。

**修改分级速记**：
- **L0 只读分析**：看报告、跑统计、画临时图 —— 无需投票。
- **L1 普通实现**（如新增分析器/测试）：至少一名同领域审阅者 + 自动化验证。
- **L2 高风险数据/模型变更**：专家组审计、投票、迁移与恢复演练。
- **L3 宪章修订**：正式修订案 + 专家组审计投票 + 保留旧版本。

---

## 十、可追溯性与交接

所有操作应可追溯。最近一次交接记录示例：`docs/HANDOFF-2026-09-11.md`（含数据范围、DB/审计链哈希、操作日志、回滚方案、复现命令）。

复现关键命令（来自交接记录，可独立验证）：

```bash
python run_update_cycle.py          # 期望: Update cycle PASS
python scan_leakage.py --db sd3d_history.sqlite3   # 期望: PASS; scanned=2
python extract_predictions.py       # 重新导出 predictions/extracted_predictions.csv
```

> 截至 2026-09-11 交接时点：数据范围 `draws` 表 **7750 行**，期号 **2004001 → 2026243**，最新开奖日 **2026-09-10**。该日期的 2026244 期尚未开奖，故当时冻结文件为 `pending`，待开奖后下轮更新自动完成盲评。

---

## 十一、常见问题

- **`No new draw rows; existing SQLite and transaction log were preserved.`**
  正常。说明官网还没有更新的期号（例如当天的开奖尚未公布）。库与日志原样保留，不会丢失。
- **`Leakage scan: FAIL; scanned=9` + 流水线停止**
  表示某个 `predictions/frozen-*.json` 里出现了实际结果字段（泄漏）。注意：**对照文件 `*-comparison.json` 不应被当作冻结产物**——脚本已用 `if "-comparison" not in name` 过滤。若仍 FAIL，检查是否有手写的冻结文件误带入 `actual` 字段。
- **`KeyError: 'run_id'`**
  通常是把 `-comparison.json` 当成冻结文件喂给 `record_outcomes.py`。冻结文件才有 `run_id`，对照文件没有。
- **想看“到底预测了什么、命中没”**
  跑 `extract_predictions.py`，打开 `predictions/extracted_predictions.csv`（Excel/表格软件即可看）。
- **`.venv` 不存在**
  见第二节，`python -m venv .venv` 即可（纯标准库，无需安装依赖）。

---

## 十二、目录速览

```text
F:\PythonProjects1\3D\
├── README.md                 # 本文件
├── AGENTS.md / PROJECT_CHARTER.md
├── run_update_cycle.py       # 日常端到端入口（推荐）
├── run_pipeline.py           # 只读分析流水线入口
├── fetch_sd3d.py             # 增量采集
├── validate_sd3d.py          # 质量门禁
├── predict_sd3d.py           # 冻结下一期候选
├── compare_prediction.py     # 盲评对照
├── record_outcomes.py        # 盲评档案入库
├── extract_predictions.py    # 导出 CSV（新手友好）
├── scan_leakage.py           # 泄漏扫描
├── evidence_brain.py         # 综合证据判断
├── model_gate.py             # 模型晋级门槛
├── docs/                     # 治理与架构文档（必读）
├── tests/                    # 单元测试
├── predictions/              # 冻结预测 + 对照（运行产物）
├── reports/                  # 所有分析报告（运行产物）
├── raw_snapshots/            # 原始网页快照（证据资产）
├── scratch/                  # 归档/实验性脚本（如 3D.py）
└── sd3d_history.sqlite3      # 权威数据库（运行产物，被 git 忽略）
    sd3d_history.jsonl        # 哈希链审计日志（运行产物）
```

> 运行产物（`reports/`、`predictions/`、`raw_snapshots/`、`*.sqlite3`、`*.jsonl`、CSV）默认不进 Git，见第六节与 `.gitignore`。
