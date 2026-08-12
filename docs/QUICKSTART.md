# 第一阶段运行方式

所有命令使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe fetch_sd3d.py
.\.venv\Scripts\python.exe analyze_sd3d.py
.\.venv\Scripts\python.exe backtest_sd3d.py
.\.venv\Scripts\python.exe validate_sd3d.py
.\.venv\Scripts\python.exe predict_sd3d.py
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
