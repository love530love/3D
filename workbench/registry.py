"""Function registry for the workbench.

Each entry describes one orchestratable action: which script to run, with what
arguments, its risk tier (per PROJECT_CHARTER.md Article 6), and whether it
requires explicit confirmation. Arguments may contain path tokens (\"{DB}\",
\"{LOG}\", \"{RAW}\", \"{REPORTS}\", \"{DECISIONS}\", \"{BACKUPS}\", \"{PRED}\",
\"{ROOT}\") that are resolved against the project root at runtime.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DB = ROOT / "sd3d_history.sqlite3"
LOG = ROOT / "sd3d_history.jsonl"
RAW = ROOT / "raw_snapshots"
REPORTS = ROOT / "reports"
DECISIONS = ROOT / "docs" / "decisions"
BACKUPS = ROOT / "backups"
PRED = ROOT / "predictions"

TOKENS = {
    "DB": str(DB),
    "LOG": str(LOG),
    "RAW": str(RAW),
    "REPORTS": str(REPORTS),
    "DECISIONS": str(DECISIONS),
    "BACKUPS": str(BACKUPS),
    "PRED": str(PRED),
    "ROOT": str(ROOT),
}

# Risk tiers mirror PROJECT_CHARTER.md Article 6.
# L0 = read-only analysis, L1 = implementation (no data-semantics change),
# L2 = high-risk (data/model change) -> requires confirmation.

FUNCTIONS: list[dict] = [
    {
        "id": "validate",
        "title": "数据校验 validate",
        "script": "validate_sd3d.py",
        "args": ["--db", "{DB}", "--log", "{LOG}", "--raw-dir", "{RAW}"],
        "risk": "L1",
        "category": "数据",
        "desc": "校验 SQLite / JSONL / 原始快照 的完整性与哈希链。",
        "confirm": False,
    },
    {
        "id": "fetch",
        "title": "增量抓取 fetch",
        "script": "fetch_sd3d.py",
        "args": ["--db", "{DB}", "--log", "{LOG}"],
        "risk": "L1",
        "category": "数据",
        "desc": "抓取最新开奖并追加到权威存储（追加式，不可变）。",
        "confirm": False,
    },
    {
        "id": "analyze",
        "title": "基础分析 analyze",
        "script": "analyze_sd3d.py",
        "args": ["--db", "{DB}"],
        "risk": "L1",
        "category": "分析",
        "desc": "频率、分布等基础统计，产出分析快照。",
        "confirm": False,
    },
    {
        "id": "diagnose",
        "title": "随机性诊断 diagnose",
        "script": "diagnose_sd3d.py",
        "args": ["--db", "{DB}", "--out", "{REPORTS}/randomness-latest.json"],
        "risk": "L1",
        "category": "分析",
        "desc": "卡方均匀性、游程、滞后相关、置换峰检测等多角度随机性诊断。",
        "confirm": False,
        "params": [
            {"name": "随机种子 seed", "flag": "--seed", "type": "int", "default": 20260812, "help": "置换检验随机种子"},
            {"name": "置换次数 permutations", "flag": "--permutations", "type": "int", "default": 500, "help": "置换检验重复次数"},
        ],
    },
    {
        "id": "evaluate",
        "title": "模型评估 evaluate",
        "script": "evaluate_models.py",
        "args": ["--db", "{DB}", "--out", "{REPORTS}/models-latest.json"],
        "risk": "L1",
        "category": "模型",
        "desc": "遍历 REGISTRY 评估各候选模型基线。",
        "confirm": False,
        "params": [
            {"name": "最小训练 min_train", "flag": "--min-train", "type": "int", "default": 500, "help": "最小训练样本"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "候选个数"},
        ],
    },
    {
        "id": "screening",
        "title": "模型筛选 screening",
        "script": "model_screening.py",
        "args": ["--db", "{DB}"],
        "risk": "L1",
        "category": "模型",
        "desc": "多家族 challenger 评分（频率/近期/马尔可夫等）。",
        "confirm": False,
    },
    {
        "id": "probability",
        "title": "概率度量 probability",
        "script": "probability_metrics.py",
        "args": ["--db", "{DB}", "--out", "{REPORTS}/probability-latest.json"],
        "risk": "L1",
        "category": "模型",
        "desc": "各 spec 的 log-loss / 校准，BH-FDR 多重比较校正。",
        "confirm": False,
        "params": [
            {"name": "最小训练 min_train", "flag": "--min-train", "type": "int", "default": 500, "help": "最小训练样本"},
            {"name": "平滑 alpha", "flag": "--alpha", "type": "float", "default": 1.0, "help": "分布平滑系数（拉普拉斯）"},
        ],
    },
    {
        "id": "drift",
        "title": "漂移检测 drift",
        "script": "drift_sd3d.py",
        "args": ["--db", "{DB}"],
        "risk": "L1",
        "category": "模型",
        "desc": "检测候选模型表现漂移并给出动作建议。",
        "confirm": False,
    },
    {
        "id": "compare",
        "title": "模型对比 compare",
        "script": "compare_models_stats.py",
        "args": ["--db", "{DB}", "--out", "{REPORTS}/model-comparison-latest.json"],
        "risk": "L1",
        "category": "模型",
        "desc": "Bootstrap 对比 + Benjamini-Hochberg 校正 p 值。",
        "confirm": False,
        "params": [
            {"name": "最小训练 min_train", "flag": "--min-train", "type": "int", "default": 500, "help": "最小训练样本"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "候选个数"},
            {"name": "重复 repeats", "flag": "--repeats", "type": "int", "default": 300, "help": "Bootstrap 重复次数"},
            {"name": "随机种子 seed", "flag": "--seed", "type": "int", "default": 20260812, "help": "随机种子"},
        ],
    },
    {
        "id": "gate",
        "title": "模型闸门 gate",
        "script": "model_gate.py",
        "args": [],
        "risk": "L1",
        "category": "模型",
        "desc": "依据各 challenger 自身 log-loss 与校正 p 值决定可否升级。",
        "confirm": False,
    },
    {
        "id": "outcomes",
        "title": "结果分析 outcomes",
        "script": "analyze_outcomes.py",
        "args": ["--db", "{DB}"],
        "risk": "L1",
        "category": "盲评",
        "desc": "盲评命中、误删率、Brier/LogLoss 等结果统计。",
        "confirm": False,
    },
    {
        "id": "leakage",
        "title": "泄漏扫描 leakage",
        "script": "scan_leakage.py",
        "args": ["--db", "{DB}"],
        "risk": "L1",
        "category": "合规",
        "desc": "扫描未来信息泄漏、冻结规则违规等合规风险。",
        "confirm": False,
    },
    {
        "id": "brain",
        "title": "综合研判 brain",
        "script": "evidence_brain.py",
        "args": [],
        "risk": "L1",
        "category": "研判",
        "desc": "汇总各报告给出综合 verdict（是否有稳定优势）。",
        "confirm": False,
    },
    {
        "id": "predict",
        "title": "冻结预测 predict",
        "script": "predict_sd3d.py",
        "args": ["--db", "{DB}"],
        "risk": "L1",
        "category": "盲评",
        "desc": "在未知下期前冻结下一期候选（盲评前置）。",
        "confirm": False,
        "params": [
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "冻结候选个数"},
        ],
    },
    {
        "id": "compare_pending",
        "title": "盲评对比 pending",
        "script": "__compare_pending__",
        "args": [],
        "risk": "L1",
        "category": "盲评",
        "desc": "对尚未对比的冻结预测逐一与真实开奖盲评。",
        "confirm": False,
    },
    {
        "id": "pipeline",
        "title": "全流程 pipeline",
        "script": "run_pipeline.py",
        "args": ["--db", "{DB}", "--log", "{LOG}", "--raw-dir", "{RAW}", "--bootstrap-repeats", "300"],
        "risk": "L1",
        "category": "全流程",
        "desc": "按确定性顺序跑完校验→分析→诊断→评估→筛选→概率→漂移→对比→闸门→结果→泄漏→研判→契约→进化草案→教学→单测。",
        "confirm": False,
    },
    {
        "id": "update_cycle",
        "title": "增量更新周期 update_cycle",
        "script": "run_update_cycle.py",
        "args": [],
        "risk": "L1",
        "category": "全流程",
        "desc": "盲评对比→抓取→校验→记录结果→(无待处理时)冻结下一期。会写入数据库（追加）。",
        "confirm": False,
    },
    {
        "id": "backtest",
        "title": "严格回测 backtest",
        "script": "backtest_sd3d.py",
        "args": ["--db", "{DB}", "--out", "{REPORTS}"],
        "risk": "L1",
        "category": "回测",
        "desc": "扩展窗口严格时间顺序回测，与均匀随机基线比较。",
        "confirm": False,
        "params": [
            {"name": "最小训练样本 min_train", "flag": "--min-train", "type": "int", "default": 500, "help": "扩展窗口起点所需训练期数"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "每期生成候选个数"},
        ],
    },
    {
        "id": "evolution_proposal",
        "title": "生成进化提案 draft",
        "script": "generate_evolution_proposal.py",
        "args": [],
        "risk": "L1",
        "category": "治理",
        "desc": "根据 brain/drift/outcomes 自动起草进化提案（DRAFT，禁止自动实施）。",
        "confirm": False,
    },
    {
        "id": "external_coupling",
        "title": "外部/日历耦合探针 external_coupling",
        "script": "workbench/external_coupling.py",
        "args": ["--db", "{DB}", "--out", "{REPORTS}/external-coupling-latest.json"],
        "risk": "L1",
        "category": "探测",
        "desc": "从开奖日期派生星期/周末/月份/月初月末，卡方独立性 + 均值置换检验探测外部状态→开奖耦合，BH-FDR 校正。",
        "confirm": False,
        "params": [
            {"name": "置换次数 permutations", "flag": "--permutations", "type": "int", "default": 400, "help": "均值置换检验重复次数"},
        ],
    },
    {
        "id": "near_miss_ensemble",
        "title": "近失集成/元学习 near_miss_ensemble",
        "script": "workbench/near_miss_ensemble.py",
        "args": ["--db", "{DB}", "--out", "{REPORTS}/near-miss-ensemble-latest.json"],
        "risk": "L1",
        "category": "探测",
        "desc": "收割近失假设（基桩族+合成feats+确定性mini生成），投票/堆叠集成，严格 OOS 盲窗 vs 随机基线 + FDR + 组合 p。",
        "confirm": False,
        "params": [
            {"name": "训练窗口 last_n", "flag": "--last-n", "type": "int", "default": 200, "help": "近失选择所用训练窗口大小"},
            {"name": "盲窗 oos_n", "flag": "--oos-n", "type": "int", "default": 60, "help": "OOS 盲评窗口大小"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "每期生成候选个数"},
        ],
    },
    {
        "id": "teaching",
        "title": "教学报告 teaching",
        "script": "build_teaching_report.py",
        "args": [],
        "risk": "L1",
        "category": "治理",
        "desc": "生成教学报告并带认识论边界守卫（禁止宣称不可预测）。",
        "confirm": False,
    },
    {
        "id": "rollback",
        "title": "回溯/回滚 rollback",
        "script": "__rollback__",
        "args": [],
        "risk": "L2",
        "category": "治理",
        "desc": "列出可恢复点并回滚到选定系统版本（先安全快照，需确认）。",
        "confirm": True,
    },
    {
        "id": "multi_method",
        "title": "多方法对比 multi_method",
        "script": "__multi_method__",
        "args": [],
        "risk": "L1",
        "category": "对比",
        "desc": "底层多种预测方式共存：每种方法严格时间顺序预测最近一期与近 N 期，对比实开并给出偏差度量（精确/位命中/数字偏差/log-loss）。",
        "confirm": False,
        "params": [
            {"name": "回看期数 last_n", "flag": "--last-n", "type": "int", "default": 12, "help": "严格时间顺序窗口期数"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "每方法候选个数"},
            {"name": "分布平滑 alpha", "flag": "--alpha", "type": "float", "default": 0.1, "help": "分布平滑系数"},
            {"name": "历史对照偏移 history_offset", "flag": "--history-offset", "type": "int", "default": 2, "help": "历史预测对照期 = 最新期 - 此偏移（默认2即最新前两期，如2026243）"},
        ],
    },
    {
        "id": "history_stats",
        "title": "历史与统计 history_stats",
        "script": "__history_stats__",
        "args": [],
        "risk": "L1",
        "category": "对比",
        "desc": "人类视觉管理：历史开奖原始表、和值/跨度走势、官网式多维统计（各位频率+遗漏/奇偶大小质合/组选类型/冷热号）、历史预测滚动对照。只读权威库，不写不改。",
        "confirm": False,
        "params": [
            {"name": "回看期数 window", "flag": "--window", "type": "int", "default": 60, "help": "历史开奖表与走势回看期数"},
            {"name": "预测对照期数 pred_window", "flag": "--pred-window", "type": "int", "default": 20, "help": "历史预测滚动对照期数（严格时间前向）"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "各方法候选个数"},
            {"name": "分布平滑 alpha", "flag": "--alpha", "type": "float", "default": 0.1, "help": "分布平滑系数"},
        ],
    },
    {
        "id": "predictive_arena",
        "title": "模型竞技场 predictive_arena",
        "script": "__predictive_arena__",
        "args": [],
        "risk": "L1",
        "category": "对比",
        "desc": "诚实回测擂台：多家族候选方案（含联合整体/和值条件/修偏均值回归/ML逻辑回归教学）严格时间前向预测，逐一与均匀随机基线做精确命中率+校准log-loss的二项分布显著性检验，置顶诚实层结论。只读权威库。",
        "confirm": False,
        "params": [
            {"name": "回看期数 last_n", "flag": "--last-n", "type": "int", "default": 200, "help": "严格时间顺序回测期数（越大统计功效越高；ML 方案较耗时）"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "每方案候选个数"},
            {"name": "分布平滑 alpha", "flag": "--alpha", "type": "float", "default": 0.1, "help": "分布平滑系数"},
        ],
    },
    {
        "id": "debate_arena",
        "title": "双阵营辩论擂台 debate_arena",
        "script": "__debate_arena__",
        "args": [],
        "risk": "L1",
        "category": "对比",
        "desc": "双阵营对抗辩论：正方(可预测派)出尽15项人类'可预测'主张（热号/冷号/和值/跨度/奇偶/质合/连号/镜像/重号/趋势/聚簇/均值回归/ML特征），反方(科学随机派)以完整统计武器库（卡方/游程/自相关/熵/Ljung-Box/最大连号/结构断点 + Benjamini-Hochberg FDR + 安慰剂/可复现/贝叶斯因子/效应量）逐一审计；双方多轮迭代，最终诚实总结谁占优、是否存在可盈利信号。只读权威库。",
        "confirm": False,
        "params": [
            {"name": "回看期数 last_n", "flag": "--last-n", "type": "int", "default": 200, "help": "严格时间顺序回测期数（越大统计功效越高；ML 方案较耗时）"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "每方案候选个数"},
            {"name": "分布平滑 alpha", "flag": "--alpha", "type": "float", "default": 0.1, "help": "分布平滑系数"},
            {"name": "FDR 阈值 q", "flag": "--fdr-q", "type": "float", "default": 0.05, "help": "多重比较校正阈值"},
            {"name": "最大轮次", "flag": "--max-rounds", "type": "int", "default": 4, "help": "对抗迭代轮次上限"},
            {"name": "直选奖金", "flag": "--prize", "type": "float", "default": 1040.0, "help": "中奖奖金（元），用于可盈利性判定"},
            {"name": "每注成本", "flag": "--cost", "type": "float", "default": 2.0, "help": "每注成本（元）"},
        ],
    },
    {
        "id": "evolution_arena",
        "title": "自进化辩论擂台 evolution_arena",
        "script": "__evolution_arena__",
        "args": [],
        "risk": "L1",
        "category": "对比",
        "desc": "① 激励账本(正方AP/反方RP + 独立Reputation + 徽章) ② AI 自进化元循环(突变/随机/综合问题生成器 + OOS盲窗 + 全局FDR递增惩罚) ③ 决策方向科学评价(单一方向标量 score=tanh(Z) + CI + TOST等价措辞)。把辩论擂台升级为闭环元系统，让正反双方主张/纠错被量化奖惩，系统随时间自我进化并持续评估'是否可预测'。只读权威库。",
        "confirm": False,
        "params": [
            {"name": "回看期数 last_n", "flag": "--last-n", "type": "int", "default": 200, "help": "严格时间顺序训练评估窗口期数"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "每主张候选个数"},
            {"name": "分布平滑 alpha", "flag": "--alpha", "type": "float", "default": 0.1, "help": "分布平滑系数"},
            {"name": "FDR 阈值 q", "flag": "--fdr-q", "type": "float", "default": 0.05, "help": "多重比较校正阈值"},
            {"name": "最大代数 max_gens", "flag": "--max-gens", "type": "int", "default": 3, "help": "自进化元循环代数上限"},
            {"name": "OOS 盲窗 oos_n", "flag": "--oos-n", "type": "int", "default": 60, "help": "末 N 期盲评窗口（训练严格限定在其中之前）"},
            {"name": "每代新主张 new_per_gen", "flag": "--new-per-gen", "type": "int", "default": 8, "help": "每代新生成(突变/合成)主张数"},
            {"name": "直选奖金", "flag": "--prize", "type": "float", "default": 1040.0, "help": "中奖奖金（元），用于可盈利性判定"},
            {"name": "每注成本", "flag": "--cost", "type": "float", "default": 2.0, "help": "每注成本（元）"},
        ],
    },
    {
        "id": "selfdrive",
        "title": "自驱动进化引擎 selfdrive",
        "script": "__selfdrive__",
        "args": [],
        "risk": "L1",
        "category": "对比",
        "desc": "离线可跑的自驱动循环：预测模型竞技场 + 双阵营对抗 + 进化引擎 -> 深度反思日志(自适应下一轮策略) -> 探索前自动 checkpoint 打点，若本批 fitness 回归则自动 rollback 还原重试。体现 ai+human+deep 三种智能。",
        "confirm": False,
        "params": [
            {"name": "批次标签 label", "flag": "--label", "type": "text", "default": "batch-auto", "help": "批次标识，用于快照与日志"},
            {"name": "策略模式 mode", "flag": "--mode", "type": "text", "default": "standard", "help": "standard / aggressive / conservative"},
            {"name": "回看期数 last_n", "flag": "--last-n", "type": "int", "default": 200, "help": "严格时间顺序窗口期数"},
            {"name": "候选数 top_k", "flag": "--top-k", "type": "int", "default": 10, "help": "每主张候选个数"},
            {"name": "FDR 阈值 q", "flag": "--fdr-q", "type": "float", "default": 0.05, "help": "多重比较校正阈值"},
            {"name": "关闭回归回滚", "flag": "--no-rollback", "type": "text", "default": "", "help": "填 1 关闭自动回滚（留空=开启）"},
        ],
    },
    {
        "id": "roles",
        "title": "角色注册表 roles",
        "script": "__roles__",
        "args": [],
        "risk": "L1",
        "category": "治理",
        "desc": "自描述角色注册表：list 列出全部角色契约（任意 AI 接入即读）；describe --id X 查看某角色；register --spec 新角色.json 经裁判团+守门员审批后激活。是'进化能力'项目内固化的单一真相源。",
        "confirm": False,
        "params": [
            {"name": "动作 action", "flag": "--action", "type": "text", "default": "list", "help": "list / describe / register"},
            {"name": "角色 id", "flag": "--id", "type": "text", "default": "", "help": "describe 时填写"},
            {"name": "spec 路径", "flag": "--spec", "type": "text", "default": "", "help": "register 时填写 new_role.json 路径"},
            {"name": "审批人", "flag": "--approver", "type": "text", "default": "", "help": "register 时 >=2 个来自 {referee,gatekeeper,human_principal}"},
        ],
    },
]


def by_id(func_id: str) -> dict | None:
    for f in FUNCTIONS:
        if f["id"] == func_id:
            return f
    return None


def resolve_args(args: list[str]) -> list[str]:
    out = []
    for a in args:
        for tok, val in TOKENS.items():
            a = a.replace("{" + tok + "}", val)
        out.append(a)
    return out
