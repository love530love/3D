# 第一阶段运行方式

所有命令使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe fetch_sd3d.py
.\.venv\Scripts\python.exe analyze_sd3d.py
.\.venv\Scripts\python.exe backtest_sd3d.py
.\.venv\Scripts\python.exe validate_sd3d.py
.\.venv\Scripts\python.exe predict_sd3d.py
.\.venv\Scripts\python.exe diagnose_sd3d.py
.\.venv\Scripts\python.exe evaluate_models.py
.\.venv\Scripts\python.exe probability_metrics.py
.\.venv\Scripts\python.exe compare_models_stats.py
.\.venv\Scripts\python.exe build_teaching_report.py
.\.venv\Scripts\python.exe run_pipeline.py
.\.venv\Scripts\python.exe evidence_brain.py
.\.venv\Scripts\python.exe drift_sd3d.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run_update_cycle.py
.\.venv\Scripts\python.exe record_outcomes.py
```

分析器只读打开 `sd3d_history.sqlite3`，在 `reports/` 中生成带运行 ID 的 JSON 报告和 manifest。报告包含：

- 期数范围和样本数量
- 数字、位置、和值和形态统计
- 熵与重复形态
- 均匀随机基线
- 频率候选实验输出
- 排除规则及误删警告

当前阶段的候选排序只是教学对照，不是预测模型。下一阶段会加入严格的 expanding-window 回测、预测冻结文件、盲评和实际结果对比。

`backtest_sd3d.py` 已提供第一版 expanding-window 回测：每一期只使用之前的数据生成候选，再记录实际开奖，最后与均匀随机基线比较。`frozen_predictions` 用于后续盲评和新一期结果对比。

`validate_sd3d.py` 是数据质量门禁，会检查 SQLite 字段、期号、开奖号码和 JSONL 哈希链。质量门禁失败时，不应继续训练或发布报告。

`predict_sd3d.py` 会冻结下一期候选。开奖数据更新后，用预测文件运行：

```powershell
.\.venv\Scripts\python.exe compare_prediction.py .\predictions\frozen-<period>-<run-id>.json
```

若目标期号尚未入库，对比程序返回 `Pending`，不会读取或猜测实际结果。

`diagnose_sd3d.py` 生成均匀性、游程、滞后相关和置换检验报告。它是随机性诊断，不是预测器；多个检验必须整体解释，不能挑选单个有利 p 值。

`evaluate_models.py` 使用统一时间协议评估模型注册表中的基线和 challenger。新模型必须实现相同的 `predict(train, top_k)` 接口，并与均匀基线同表比较。

`probability_metrics.py` 评估完整位置概率分布，输出 Brier Score、Log Loss、Top-1 和简化校准误差。概率指标比单纯命中率更能发现过度自信和不可复现的模型。

`compare_models_stats.py` 用配对 Bootstrap 估计 challenger 相对均匀基线的差异区间；`build_teaching_report.py` 汇总当前质量、随机性、模型和概率报告。

推荐日常使用 `run_pipeline.py`。它先执行质量门禁，只有门禁通过才继续生成分析、回测、概率、Bootstrap 和教学报告。

`evidence_brain.py` 汇总所有报告并输出综合判断。它是受治理约束的证据中枢，不会自动改代码、删数据或把实验模型升级为正式模型。

`drift_sd3d.py` 比较近期窗口与历史窗口的数字、和值和形态分布，只输出 `REVIEW_ONLY` 复核信号，不自动追逐漂移。

原始快照可以离线重放：

```powershell
.\.venv\Scripts\python.exe replay_snapshot.py .\raw_snapshots\<sha256>.html
```

这不会访问网络。核心回归测试使用：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

日常更新推荐使用 `run_update_cycle.py`：它先处理已有冻结预测，再增量抓取，执行质量门禁和分析流水线，最后在没有待盲评目标时冻结新预测。离线演练使用 `--no-fetch --skip-pipeline`。

`record_outcomes.py` 将冻结预测和实际开奖写入 SQLite 的 `prediction_outcomes` 表，按 `prediction_id` 去重，支持长期偏差、漂移和模型版本分析。
