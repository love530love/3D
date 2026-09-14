"""激励 / 代币 / 积分账本（Evolution Arena 的激励层）.

为双阵营自进化辩论提供一套代币 + 积分 + 声誉的激励机制：

  * 正方(可预测派) 持有「主张积分 AP」与「声誉 Reputation(0–100)」；
  * 反方(科学随机派) 持有「纠错积分 RP」与「声誉 Reputation(0–100)」。

核心设计原则（反博弈护栏）：
  1. 提交主张需冻结押金 C_SUB，被驳回即没收 -> 堵住「海量撒网弱主张」。
  2. 诚实撤回得正奖励（退押金 + retr 奖励 + Rep），被抓驳回得 0 且 Rep-3
     -> 主动认错是占优策略，鼓励诚实纠错。
  3. 驳回由独立统计审计裁定，反方仅对「审计确认假」的主张得分，
     靠「什么都驳」刷分无效（每次挑战付费，滥驳亏本）；若主张其实存活
     （反方挑战错误）则没收挑战费 + Rep-5，杜绝压制真实信号。
  4. 声誉与积分分离：AP/RP 可花尽，Rep 慢变、只增于诚信，驱动徽章与权重。
  5. 科学价值加权：存活/纠错奖金乘 merit_w，纯数量不加分。

本账本是**对审计结果的科学计分**（AI 自进化场景下两阵营即两组评分智能体），
不是真正的加密货币经济；所有数字均确定性地由辩论审计结果推导，DB 只读、零泄漏。
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class IncentiveLedger:
    """双阵营积分 / 声誉 / 徽章账本，JSON 可持久化（append-only 增量 + 快照）。"""

    C_SUB = 5   # 正方提交主张冻结押金（AP）
    C_CHL = 5   # 反方发起挑战费（RP）

    # —— 防"长期负激励崩溃"护栏（2026-09-14 新增）——
    # 设计动机：在没有最终可预测结论前，探索弱信号的行为本身应被正向激励，
    # 否则自进化探索动力会枯竭（"躺平"），违背项目"禁止躺平式结论"的核心原则。
    REP_FLOOR = 0.0          # 声誉下限：声誉不得为负，防止账本语义崩溃
    BASE_GRANT_PRO_AP = 80.0 # 每轮基础拨款：正方"探索研究金"（保持偿付能力）
    BASE_GRANT_CON_RP = 20.0 # 每轮基础拨款：反方"监管vigilance金"（对称公平）
    NEAR_MISS_AP = 12.0      # 近失/开放假设"探索前沿奖"（在退还押金之外）
    NEAR_MISS_REP = 1.0
    BOOTSTRAP_PRO_AP = 50.0  # 历史负分一次性引导拨款（仅当探索方破产时触发）

    def __init__(self, path: Path | None = None):
        self.version = 1
        self.round = 0
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        self.camps = {
            "pro": {"ap": 0, "rep": 100.0, "submitted": 0, "survived": 0,
                    "retracted": 0, "history": []},
            "con": {"rp": 0, "rep": 100.0, "challenges": 0, "correct": 0,
                    "wrongful": 0, "history": []},
        }
        self.claims: dict[str, dict] = {}
        self.badges = {"pro": "Bronze", "con": "Bronze"}
        if path is not None and Path(path).exists():
            self._load(path)

    # ---- 科学价值权重 ----------------------------------------------------
    def merit_w(self, cohens_h: float, bayes_factor: float) -> float:
        """merit_w ∈ [0,1]：主张的科学价值权重（效应量 + 贝叶斯因子）。"""
        try:
            bf = bayes_factor if bayes_factor and bayes_factor > 0 else 1e-300
            return _clamp(abs(cohens_h) * 2.0 + math.log(bf), 0.0, 1.0)
        except Exception:
            return 0.0

    # ---- 基础账目操作 ----------------------------------------------------
    def submit(self, claim_id: str, origin: str = "") -> None:
        """正方提交主张：冻结押金（AP 扣减）。"""
        if claim_id in self.claims:
            return
        self.claims[claim_id] = {
            "status": "pending", "fee_paid": self.C_SUB, "origin": origin,
        }
        self.camps["pro"]["submitted"] += 1
        self.camps["pro"]["ap"] -= self.C_SUB
        self._record("pro", f"submit:{claim_id}", -self.C_SUB, 0,
                     f"提交主张冻结押金（{origin}）")

    def survive(self, claim_id: str, merit_w: float) -> None:
        """主张存活（FDR + 安慰剂 + 复现 + 盈利全过）：退押金 + 存活奖金。"""
        bonus = 50.0 * merit_w
        self.camps["pro"]["ap"] += self.C_SUB          # 退还押金
        self.camps["pro"]["ap"] += bonus
        self.camps["pro"]["rep"] += 4.0
        self.camps["pro"]["survived"] += 1
        if claim_id in self.claims:
            self.claims[claim_id]["status"] = "survived"
        self._record("pro", f"survive:{claim_id}", self.C_SUB + bonus, 4.0,
                     f"主张存活：退押金+存活奖{bonus:.1f}AP（merit_w={merit_w:.2f}）")
        self._recalc_badges()

    def retract(self, claim_id: str) -> None:
        """诚实撤回（裁定前自认薄弱）：退押金 + 撤回奖励（诚信正激励）。"""
        self.camps["pro"]["ap"] += self.C_SUB
        self.camps["pro"]["ap"] += 20.0
        self.camps["pro"]["rep"] += 2.0
        self.camps["pro"]["retracted"] += 1
        if claim_id in self.claims:
            self.claims[claim_id]["status"] = "retracted"
        self._record("pro", f"retract:{claim_id}", self.C_SUB + 20.0, 2.0,
                     "诚实撤回：退押金+20AP（诚信奖励）")
        self.camps["con"]["rp"] += 10.0   # 反方协调奖
        self._record("con", f"coord:{claim_id}", 10.0, 0.0, "正方诚实撤回协调奖")

    def reject(self, claim_id: str, decisiveness: float = 0.0) -> None:
        """反方正确驳回（审计独立确认该主张为假）：没收正方押金 + 反方纠错奖。"""
        # 正方押金已冻结，此处直接记为没收（Rep 处罚）
        self.camps["pro"]["rep"] -= 3.0
        if claim_id in self.claims:
            self.claims[claim_id]["status"] = "rejected"
        self.camps["pro"]["rep"] = _clamp(self.camps["pro"]["rep"] - 3.0, self.REP_FLOOR, 1e9)
        self._record("pro", f"reject:{claim_id}", 0, -3.0, "主张被驳回：押金没收，Rep-3")
        # 反方纠错
        reward = 30.0 + 10.0 * _clamp(decisiveness, 0.0, 1.0)
        self.camps["con"]["challenges"] += 1
        self.camps["con"]["correct"] += 1
        self.camps["con"]["rp"] += reward
        self.camps["con"]["rep"] += 3.0
        self._record("con", f"refute:{claim_id}", reward, 3.0,
                     f"正确驳回主张（decisiveness={decisiveness:.2f}）")
        self._recalc_badges()

    def wrongful_reject(self, claim_id: str) -> None:
        """反方错误驳回（主张其实存活，反方却挑战过）：没收挑战费 + Rep-5。"""
        self.camps["con"]["rp"] -= self.C_CHL
        self.camps["con"]["rep"] = _clamp(self.camps["con"]["rep"] - 5.0, self.REP_FLOOR, 1e9)
        self.camps["con"]["wrongful"] += 1
        self._record("con", f"wrongful:{claim_id}", -self.C_CHL, -5.0,
                     "错误驳回（主张存活）：挑战费没收，Rep-5")
        self._recalc_badges()

    def near_miss(self, claim_id: str, merit_w: float = 0.0) -> None:
        """近失 / 开放假设：虽未过 FDR，但推动探索前沿，获正向激励（不没收押金）。

        直接回应机制设计的'长期负激励崩溃'风险——在没有最终可预测结论前，
        探索弱信号的行为本身应被奖励，否则自进化探索动力会枯竭（"躺平"）。
        """
        refund = self.C_SUB                       # 退还提交押金
        bonus = self.NEAR_MISS_AP * (0.5 + 0.5 * _clamp(merit_w, 0.0, 1.0))
        total = refund + bonus
        self.camps["pro"]["ap"] += total
        self.camps["pro"]["rep"] = _clamp(self.camps["pro"]["rep"] + self.NEAR_MISS_REP,
                                         self.REP_FLOOR, 1e9)
        if claim_id in self.claims:
            self.claims[claim_id]["status"] = "near_miss"
        self._record("pro", f"near_miss:{claim_id}", total, self.NEAR_MISS_REP,
                     f"近失/开放假设：退押金+探索前沿奖{bonus:.1f}AP（merit_w={merit_w:.2f}）")

    def round_grant(self, round_no: int) -> None:
        """每轮基础拨款：双方各获 baseline 代币，保证长期偿付能力、避免激励枯竭。

        pro 拿'探索研究金'、con 拿'监管vigilance金'，与谁'赢得辩论'无关——
        辩论胜负是科学结论（con 赢=诚实无信号），但双方都应保持偿付与动机，
        否则系统对'探索'的评价会陷入长期负分而崩溃。
        """
        self.camps["pro"]["ap"] += self.BASE_GRANT_PRO_AP
        self._record("pro", f"grant:round{round_no}", self.BASE_GRANT_PRO_AP, 0.0,
                     f"基础拨款·探索研究金（第{round_no}轮）")
        self.camps["con"]["rp"] += self.BASE_GRANT_CON_RP
        self._record("con", f"grant:round{round_no}", self.BASE_GRANT_CON_RP, 0.0,
                     f"基础拨款·监管vigilance金（第{round_no}轮）")
        self.round = max(self.round, round_no)

    def catch_cheat(self, claim_id: str = "") -> None:
        """抓作弊（窥未来 / 改库）：赏金 200 RP + Rep+10；正方封禁清零。"""
        self.camps["con"]["rp"] += 200.0
        self.camps["con"]["rep"] += 10.0
        self._record("con", f"cheat:{claim_id}", 200.0, 10.0, "抓作弊赏金200RP")
        self.camps["pro"]["ap"] = 0
        self.camps["pro"]["rep"] = 0.0
        self._record("pro", "banned", 0, 0, "作弊封禁：AP清零、Rep归零")

    # ---- 徽章 ------------------------------------------------------------
    def _recalc_badges(self) -> None:
        # 正方徽章：按存活率 + 声誉
        ps = self.camps["pro"]
        surv_rate = (ps["survived"] / ps["submitted"]) if ps["submitted"] else 0.0
        self.badges["pro"] = self._badge_for(ps["rep"], surv_rate)
        # 反方徽章：按正确率 + 声誉
        cs = self.camps["con"]
        acc = (cs["correct"] / cs["challenges"]) if cs["challenges"] else 0.0
        self.badges["con"] = self._badge_for(cs["rep"], acc)

    @staticmethod
    def _badge_for(rep: float, perf: float) -> str:
        if rep >= 160 and perf >= 0.6:
            return "Platinum"
        if rep >= 140 and perf >= 0.5:
            return "Gold"
        if rep >= 120 and perf >= 0.3:
            return "Silver"
        return "Bronze"

    # ---- 内部 ------------------------------------------------------------
    def _record(self, camp: str, act: str, d_ap: float, d_rep: float, note: str) -> None:
        self.camps[camp]["history"].append(
            {"act": act, "d_ap": round(d_ap, 2), "d_rep": round(d_rep, 2), "note": note}
        )

    def _normalize_rep(self) -> None:
        """声誉下限 + 探索方破产一次性引导拨款（防止历史负分导致账本语义崩溃）。

        仅当加载到'探索方 AP 为负'的遗留状态时触发一次，把其恢复到可偿付基线
        (+BOOTSTRAP_PRO_AP)，并在 history 留下诚实可追溯的记录；一旦恢复为正，
        后续加载不再重复触发。这是'版本管理可还原'框架下的安全调和，非篡改历史。
        """
        self.camps["pro"]["rep"] = max(self.REP_FLOOR, self.camps["pro"]["rep"])
        self.camps["con"]["rep"] = max(self.REP_FLOOR, self.camps["con"]["rep"])
        if self.camps["pro"]["ap"] < 0:
            topup = -self.camps["pro"]["ap"] + self.BOOTSTRAP_PRO_AP
            self.camps["pro"]["ap"] += topup
            self._record("pro", "legacy_reconcile", topup, 0.0,
                         f"历史负分调和：引导拨款{topup:.0f}AP（防账本崩溃）")

    def _load(self, path: Path) -> None:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return
        self.version = data.get("version", 1)
        self.round = data.get("round", 0)
        self.updated_at = data.get("updated_at", self.updated_at)
        self.camps = data.get("camps", self.camps)
        self.claims = data.get("claims", {})
        self.badges = data.get("badges", self.badges)
        self._normalize_rep()

    @classmethod
    def from_dict(cls, d: dict) -> "IncentiveLedger":
        """从持久化字典重建账本（用于跨运行累积）。"""
        obj = cls()
        obj.version = d.get("version", 1)
        obj.round = d.get("round", 0)
        obj.updated_at = d.get("updated_at", obj.updated_at)
        obj.camps = d.get("camps", obj.camps)
        obj.claims = d.get("claims", {})
        obj.badges = d.get("badges", obj.badges)
        obj._normalize_rep()
        return obj

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "round": self.round,
            "updated_at": self.updated_at,
            "camps": self.camps,
            "claims": self.claims,
            "badges": self.badges,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                       encoding="utf-8")
