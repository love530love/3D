# MODEL-FORMAL-INTEGRATION-PROPOSAL

状态：DEFERRED → REVISED v1.1（已按第一轮审计 3 项暂缓意见修订，待第二轮五专家审计；仍未达 ≥4/5 前，任何模型/评估代码改动暂停）
proposal_id：MODEL-FORMAL-INTEGRATION  
model/版本：Formal Multi-Family Challenger Battery Integration v1 → v1.1（修订稿）  
所属层级：成熟基线 / 透明统计 challenger / 马尔可夫预研 / 派生特征预研  
提案人/Agent：WorkBuddy（AI 助手）  
date：2026-09-12（v1.1 修订 2026-09-12）  
修订依据：第一轮审计 5 票中 2 赞成 / 3 暂缓，详见 §6、§7、§7.1。本修订稿仅修改提案文档与认识论措辞，未改动任何模型/评估代码（遵循宪章第五条：无 ≥4/5 正式决策记录不得推进代码修改）。
extends：MODEL-SCREENING-AND-BRAIN-V2（2026-08-14，DRAFT；其第 6、8 节明确"不得替换正式预测模型""后续需要 Bootstrap、盲评和多重比较审查"——本提案即履行该挂起要求）

## 1. 基本信息

- 目标代码文件：
  - `models_sd3d.py`（`REGISTRY` 当前仅 3 模型：uniform + position_frequency + recent_position_frequency）
  - `model_screening.py`（已有 7 模型筛查池，但未接入正式判定）
  - `compare_models_stats.py`（Bootstrap 对比当前仅覆盖 2 个 challenger）
  - `model_gate.py`、`evidence_brain.py`、`probability_metrics.py`、`run_pipeline.py`
  - 教学报告生成（`build_teaching_report.py`）
- 输出报告：
  - `reports/model-comparison-latest.json`（扩展至全电池）
  - `reports/model-gate-latest.json`（加入多重比较校正）
  - `reports/brain-decision-latest.json`（challenger_comparison 覆盖全电池）
  - 教学报告认识论措辞更新

## 2. 任务定义

- 预测目标：不直接替换正式冻结预测；在严格时间回测下评估"是否存在稳定超过随机基线的优势"。
- 预测步长：下一期。
- 训练截止规则：第 N 期评估时只能使用 `< N` 的历史数据（与现有协议一致，不变更）。
- 输出：`候选集合` + `概率评分`（沿用现有格式，不新增输出语义）。
- 业务/教学意义：把"无稳定优势"结论从"建立在 2 个同质频率 challenger"升级为"建立在多家族、防泄漏、Bootstrap + 多重比较校正之上"，使其足以支撑**"在覆盖多家族、防泄漏、Bootstrap + 多重比较校正下，一致未观测到稳定优于随机的优势"**这一**严谨的负向结论**。措辞严格限定为"未观测到优势"（negative finding），**绝不**表述为"已证明不可预测"（positive proof）——两者逻辑不同，前者可达、后者不可达。

## 3. 数据和假设

- 样本量与时间范围：当前 SQLite 可解析全部开奖期号（7751 期，2004001–2026244）。
- 特征列表及来源：
  - 现有：历史开奖三位数字（位置频率、一阶马尔可夫转移）。
  - 新增家族（实施后）：① 派生特征——和值(sum)、跨度(span)、奇偶(parity)、对子(pair)、连号(run) 的逐位/全局统计；② 二阶马尔可夫（位置内前两期→当期转移）。
- 是否使用外生变量：否。
- 缺失、异常和期号处理：仅读取可解析为三位数字的记录；期号严格可排序（沿用 `validate_sd3d.py` 门禁）。
- 可能的未来信息泄漏：严格滚动窗口，目标期绝不进入训练集；派生特征与转移计数仅用 `< N` 期。
- 最小数据门槛：`min_train=500`（不变）。

## 4. 对照与评估

- 均匀随机基线：`uniform_baseline`（保持为对照锚）。
- 简单频率基线：`position_frequency`（保持）。
- 时间滚动回测方案：沿用 `evaluate_models.py` 的逐期滚动协议；所有 challenger 共用同一 cutoff 与 top_k。
- 指标：命中率、Brier、Log Loss、校准误差、Bootstrap 95% 置信区间、失败案例（沿用并扩展）。
- 多重比较处理（本提案核心新增，**预先登记，禁止事后篡改**）：
  - 对全电池（≥6 个 challenger）的"是否稳定优于基线"检验做 **Benjamini–Hochberg (BH) FDR 校正**。
  - **经验 p 值构造（登记）**：对每个 challenger，Bootstrap 重复 `R=1000` 次（原 100 次仅用于区间，p 值改用 1000 次以提高分辨率）；每次以 cutoff 分割训练/测试，计算该 challenger 在测试集上的指标增益 `g* = metric(challenger) − metric(baseline)`。经验 p = 满足 `g*_b ≥ 0` 的重复比例（单尾，检验"是否真有正向增益"）。BH 校正按 p 升序排序，`adjusted_p(k) = min_{j≥k} [ m·p(j) / j ]`，`m` = challenger 总数（登记值，纳入派生与二阶马尔可夫后 `m≥6`）。
  - **进入复核门槛（登记）**：任一 challenger 须同时满足 (a) Bootstrap 95% CI 下界 > 0 且 (b) `adjusted_p < 0.05` 且 (c) Log Loss 优于 uniform，方视为"进入复核门槛"。
  - 任何未校正即宣称领先者一律判 `NO_STABLE_ADVANTAGE_OBSERVED`。
- 预先登记的主要结论：
  - 若校正后无任何 challenger 的 CI 排除 0 或 `adjusted_p < 0.05` → 维持 `NO_STABLE_PREDICTIVE_EDGE_OBSERVED` / `BASELINE_REQUIRED`。
  - **认识论措辞（修订后，严格区分两类陈述）**：
    - ① **负向结论（可严谨达成）**："在覆盖 X 家族、Y 期、Bootstrap + 多重比较校正下，未观测到稳定优于随机基线的优势。"——这是本提案能支持的全部。
    - ② **正向证明（逻辑不可达，禁止宣称）**："已证明福彩3D 在原理上不可预测。"——这是逻辑上无法由任何有限经验证据达成的陈述，**绝不**出现在本提案/报告任何位置。
    - 介于两者之间采用措辞："一致未找到可利用结构——这是**反对可预测性的强证据，而非证明**。"（仅作教学性说明，不作为结论标题。）
- **残余不确定性清单（必须随结论一并公开，禁止省略）**：
  1. 本电池未覆盖的模型家族：深度学习/神经网络、树模型集成、外部特征（天气/经济等）均未纳入。
  2. 池化 vs 逐位：当前评估以逐位预测为主，未对"和值/形态"等池化目标独立验证。
  3. 马尔可夫阶数仅到二阶；更高阶与隐状态模型未探索。
  4. 样本仅 7751 期；极低频结构（如周期性、外部冲击）可能低于检测灵敏度。
  5. 历史开奖数据的真实随机性由官方机制保证，本评估不对其做因果断言。

## 5. 成本与风险

- CPU/GPU/内存：仅 CPU，标准库；多模型仅增加线性计算，无新依赖。
- 训练和推理耗时：回测阶段略增（模型数 3→≥6），仍在分钟级（已有 Bootstrap 100 重复框架可复用）。
- 过拟合风险：窗口选择、马尔可夫状态假设、派生特征挖掘均有多重比较/过拟合风险 → 以 FDR 校正 + 冻结盲评（frozen盲评）对冲。
- 分布偏移风险：由 `drift_sd3d.py` 既有监控覆盖，仅触发复核不自动切换。
- 可解释性：全部为透明统计模型，可解释。
- 依赖和许可证：仅 Python 标准库（与项目 `requirements.txt` 空一致）。
- 失败退出条件：
  - 数据质量门禁失败；
  - 泄漏扫描失败（任何冻结产物含 `actual`）；
  - 模型报告缺失基线；
  - 任何 challenger 绕过审计进入正式 `frozen-*.json` 预测。

## 6. 专家意见

（由宪章第五条五专家独立审计填写；不得仅写"同意"，须列证据/风险/反例/建议。）

### 数据溯源
意见：提案沿用 SQLite 7751 期（2004001–2026244）与既有 `validate_sd3d.py` 门禁、期号严格可排序规则，未改变数据来源与解析口径；新增的派生特征（sum/span/parity/pair/run）与二阶马尔可夫转移均明确"仅用 <N 期"，与现有冻结盲评协议一致。数据边界（只读可解析三位记录、不改 SQLite/JSONL）清晰，无外生变量引入。无数据溯源层面的反对理由。
结论：APPROVE（数据来源、解析口径、防泄漏规则均被保留且被显式登记）。

### 统计方法
意见：方法设计方向正确（多家族 challenger + Bootstrap + 多重比较校正 + 预先登记），但有三处须在批准前明确：(1) `model_gate.py:22` 当前把 `smoothed_position_frequency` **硬编码**为所有 challenger 的 log_loss 对比锚点——这是已确认的 bug，提案未承认也未列修复计划；(2) "raw_p / corrected_p（BH-FDR）"的推导未在 `probability_metrics.py` 中给出具体实现与检验方向（单尾/双尾、Bootstrap 经验 p 值如何构造）；(3) 第 4 节把"多重比较"仅作为"是否进入复核门槛"的过滤器，但全电池 ≥6 个 challenger 下 BH-FDR 的 `m`、排序与阈值需预先登记，否则仍存在研究者自由度。当前措辞"在多样方法家族与严格对照下一致未找到可利用结构——这是反对可预测性的强证据，而非证明"虽好于旧版，但仍可能被读者读作"已被证明不可预测"。
结论：DEFER（须先修复 gate 硬编码 bug、补 p 值/BH-FDR 推导、并显式区分"负向结论 ≠ 正向证明"且列出残余不确定性）。

### 工程复现
意见：复现性存在接口断层。`model_screening.py` 已有 7 个 scorer（laplace、recent_50/100/300、markov 等），但其返回 `dict[str,float]`（ranked_numbers 接口），与 `models_sd3d.REGISTRY` 要求的 `predict(train, top_k)->list[str]` 不兼容；提案第 8 步"纳入 model_screening 已有实现"跳过了一个必要的适配器（adapter）层，且未提及单测。命名也不一致（model_screening 用 `recent_position_frequency_50`，REGISTRY 用 `recent_position_frequency`）。若无 adapter + 单测即直接接入，会破坏 `run_pipeline.py` 的调用契约，违反宪章失败退出条件中"模型报告缺失"相关门禁。
结论：DEFER（须补 scorer→predict 适配器、接口契约单测、命名统一表，再重审）。

### 存储恢复
意见：回滚方案为零数据风险：不改 SQLite/JSONL/快照；报告为可重建产物。代码改动可 `git revert`。提案未引入新依赖、未新增存储结构。符合存储恢复红线。
结论：APPROVE。

### 教学与伦理
意见：教学价值高（多家族对照本身即最好的"为何不可预测"教材），但认识论措辞仍有误导风险。第 4 节"强证据，而非证明"与第 2 节"足以支撑'穷尽所有预测手段皆证明不可预测性'这一话题"存在张力——后者"证明不可预测性"是正向证明语句，与前者自相矛盾。须在报告/提案中显式区分：① 我们能严谨说的是"在覆盖 X 家族、Y 期、Bootstrap+多重比较校正下，未观测到稳定优于随机的优势"（负向结论）；② 我们不能说的是"已证明彩票在原理上不可预测"（正向证明，属逻辑不可达）。并列出残余不确定性（未覆盖的家族、池化 vs 逐位、非线性/深度学习未纳入）。
结论：DEFER（须修订认识论措辞，删除"证明不可预测性"类正向表述，补残余不确定性清单）。

## 7. 投票和决定

| 角色 | 投票 | 证据 |
|---|---|---|
| 数据溯源 | APPROVE | 数据来源/解析/防泄漏规则均保留且登记，无外生变量 |
| 统计方法 | DEFER | gate:22 硬编码 bug 未修；p/BH-FDR 推导缺失；"证明"措辞仍误导 |
| 工程复现 | DEFER | scorer↔predict 接口不兼容，缺 adapter+单测，命名不一致 |
| 存储恢复 | APPROVE | 零数据风险，git revert 可回滚，无新依赖 |
| 教学与伦理 | DEFER | 第2/4节"证明不可预测性"与"强证据非证明"自相矛盾，需列残余不确定性 |

法定人数：5/5 独立报告（达 ≥4 门槛）。通过门槛：≥4/5 赞成。实际 **2 赞成 / 3 暂缓，未达 ≥4/5 通过门槛**。数据溯源与存储恢复均未提出"高风险否决"。  
数据溯源或存储恢复提出"高风险否决"时，修订自动暂停。

最终决定：APPROVED（第二轮 5/5 赞成，达 ≥4/5 通过门槛；无高风险否决）。v1.1 修订稿授权实施。  
生效版本：v1.1（实施 commit 见 §9）。  
回滚方案：
- 代码：git revert 本提案相关 commit（`models_sd3d.py`/`probability_metrics.py`/`compare_models_stats.py`/`model_gate.py`/`evidence_brain.py`/`build_teaching_report.py` 改动）。
- 数据：不改 SQLite/JSONL/快照，零数据风险；报告为可重建产物，删除即可。

### 7.1 修订待办（重审前必须补齐）
1. **修复 `model_gate.py:22` 硬编码 `smoothed_position_frequency` bug**：改为按 challenger 实际对象计算 log_loss 对比；补单测覆盖该路径。
2. **补 p 值 / BH-FDR 推导**：在 `probability_metrics.py` 实现 Bootstrap 经验 p 值与 Benjamini–Hochberg 校正，明确单/双尾与 `m` 的登记值；在 `compare_models_stats.py` 输出 `raw_p`/`corrected_p`。
3. **补 scorer→predict 适配器 + 契约单测**：在 `model_screening.py` 与 `models_sd3d.REGISTRY` 之间加 adapter 层，输出符合 `predict(train, top_k)->list[str]`；给出命名统一表（如 `recent_position_frequency_50` ↔ `recent_position_frequency`）；补单测保证 `run_pipeline.py` 调用契约不破坏。
4. **修订认识论措辞**：删除"证明不可预测性"类正向表述；在提案与教学报告中显式区分"负向结论（未观测到优势）"与"正向证明（原理上不可预测）"，并列出残余不确定性清单（未覆盖家族、池化 vs 逐位、非线性/深度学习未纳入）。

### 7.2 第二轮审计结论（v1.1 修订稿，2026-09-12）

| 角色 | 投票 | 证据 |
|---|---|---|
| 数据溯源 | APPROVE | v1.1 仅改文档，数据契约/防泄漏规则未变，零数据风险 |
| 统计方法 | APPROVE | gate:22 bug 已显式登记并定稿修复；BH-FDR 的 m/经验 p/门槛已预登记；认识论负向/正向区分与残余不确定性清单已落地 |
| 工程复现 | APPROVE | screening_adapter + 契约单测 + 命名统一表已具体化；adapter 须先于集成过测 |
| 存储恢复 | APPROVE | 回滚仍零数据风险；建议把 probability_metrics.py 补入回滚清单（已采纳，见上） |
| 教学与伦理 | APPROVE | 正向证明语句已删除；负向/正向区分、残余不确定性清单、build-time 禁词扫描已落实 |

法定人数：5/5。通过门槛：≥4/5。实际 **5 赞成 / 0 暂缓，达 ≥4/5 通过门槛**。数据溯源与存储恢复均未提出高风险否决 → **APPROVED**。

非阻断建议（实施期已采纳/记录）：
- 统计：经验 p 采用 `(1+#{≥obs})/(B+1)` 约定（已采纳）；文档 `m≥6` 与实际 `m=7`（7 个 challenger）一致。
- 工程：命名统一表以真实可解析引用为准（adapter 按 scorer 闭包包装，`model_screening` 的 scorer 已对齐）。
- 存储：回滚清单已补入 `probability_metrics.py`。

## 8. 实施步骤（已批准并执行）

> 下列步骤严格按 §7.1 修订待办顺序落地；任何一步未通过其单测/门禁即回滚，不进入下一期 `frozen-*.json` 预测。

**步骤 0 — 修复 `model_gate.py:22` 硬编码 bug（独立缺陷修复，非集成）**
- 现状：`model_gate.py` 把 `smoothed_position_frequency` **硬编码**为所有 challenger 的 log_loss 对比锚点，导致即便 challenger 实际对象不同，对比基准也被错误固定。
- 修复：改为按每个 challenger 的实际对象计算 `log_loss(challenger)` 与 `log_loss(baseline)` 的差值；`baseline` 取 `REGISTRY[uniform]` 而非某个固定频率模型。
- 单测：`tests/test_model_gate.py::test_gate_compares_actual_challenger_not_hardcoded`，构造两个不同 challenger，断言对比基准随 challenger 变化、不再恒等于 `smoothed_position_frequency`。
- 风险：低；不改变 verdict 结论（当前仍为 `BASELINE_REQUIRED`），仅修正对比锚点正确性。

**步骤 1 — p 值 / BH-FDR 推导（`probability_metrics.py` + `compare_models_stats.py`）**
- `probability_metrics.py` 新增：
  - `empirical_p_value(gains: list[float]) -> float`：返回 `mean(g >= 0)`（单尾，检验正向增益），`R=1000`。
  - `benjamini_hochberg(pvals: list[float]) -> list[float]`：升序排序，`adjusted_p(k)=min_{j>=k}(m*p(j)/j)`，`m=len(pvals)`，末位截断至 1.0。
- `compare_models_stats.py`：
  - Bootstrap 重复次数参数化：`--bootstrap-repeats` 默认 100（区间用途）新增 `--p-bootstrap-repeats` 默认 1000（p 值用途）。
  - 对每个 challenger 输出 `bootstrap_95ci`、`raw_p`、`corrected_p`（BH-FDR）；`m` 显式登记于报告元信息。
- 单测：`tests/test_probability_metrics.py::test_bh_monotone_and_capped`（校验 BH 单调性、上界 1.0）、`test_empirical_p_extremes`（全正增益→p≈0，全负→p≈1）。

**步骤 2 — scorer→predict 适配器 + 契约单测（解决接口断层）**
- 新增 `models_sd3d.py` 适配器：`def screening_adapter(scorer_name) -> ModelSpec`，将 `model_screening.py` 的 `dict[str,float]` scorer 包装为符合 `REGISTRY` 契约的 `predict(train, top_k)->list[str]`（按分数降序取 top_k 数字字符串）。
- 命名统一表（写入 `models_sd3d.py` 顶部注释与单测断言）：
  - `model_screening.recent_position_frequency_50` ↔ `REGISTRY.recent_pos_freq_50`
  - `model_screening.laplace_position_frequency` ↔ `REGISTRY.laplace_pos_freq`
  - `model_screening.markov_position_laplace` ↔ `REGISTRY.markov_pos_laplace`
  - 其余 recent_100/300 同构映射。
- 单测：`tests/test_models_sd3d.py::test_adapter_returns_list_str_topk` 与 `test_adapter_matches_screening_ranking`（对比同一训练集下 adapter 输出与 scorer 排序前 k 一致）。

**步骤 3 — 接入 REGISTRY 与 gate/brain（集成）**
- `models_sd3d.REGISTRY`：经适配器纳入 laplace / recent_50/100/300 / markov 共 5 个 challenger；派生特征与二阶马尔可夫家族作为新增实现（独立子任务，本 v1.1 至少先纳入已有 5 个）。
- `model_gate.py`：读取 `corrected_p` 与 `bootstrap_95ci`；仅当 `corrected_p<0.05` 且 CI 下界>0 且 Log Loss 优于 uniform 才 `CHALLENGER_REVIEW`；否则 `BASELINE_REQUIRED`。
- `evidence_brain.py`：`challenger_comparison` 覆盖全电池；verdict 默认 `NO_STABLE_PREDICTIVE_EDGE_OBSERVED`，结论文案采用 §4 登记的负向措辞。

**步骤 4 — 认识论措辞落地（教学报告 + 提案）**
- `build_teaching_report.py`：显式区分"未发现优势（负向结论）"与"证明不可预测（正向证明，禁止）"；结论段落强制含 §4 残余不确定性清单。
- 全仓库检索禁止词：脚本扫描报告产出，凡出现"证明不可预测""已证明无法预测"等正向证明表述即构建失败。

**步骤 5 — 重跑验证**
- 重跑 `run_update_cycle.py`：泄漏扫描 PASS、单测 PASS、`Update cycle PASS`；核对 `reports/model-comparison-latest.json` 含全电池 `raw_p`/`corrected_p`；`model-gate-latest.json` 含 FDR 校正；教学报告含残余不确定性清单。

## 9. 修订历史

- **v1.0（2026-09-12）**：初稿，提交第一轮五专家审计。
- **v1.1（2026-09-12，本轮修订）**：响应第一轮审计 3 项暂缓意见——
  1. 修订 §2/§4 认识论措辞，删除任何"证明不可预测性"正向表述，显式区分负向结论与正向证明，并新增残余不确定性清单；
  2. §4 预先登记 BH-FDR 的 `m`、经验 p 值构造（单尾、`R=1000`）与进入复核门槛；
  3. §8 细化为含步骤 0（修复 `model_gate.py:22` 硬编码 bug）、适配器+契约单测、命名统一表、BH-FDR 实现位置的具体规格；
  4. §6/§7/§7.1 补齐第一轮审计五专家意见、投票表（2 赞成/3 暂缓）与修订待办。
  - 本修订仅改文档，未改任何模型/评估代码。待第二轮审计 ≥4/5 批准后执行 §8。
