"""Read-only model screening and prediction-distance diagnostics.

This module expands the research model pool without changing the formal
frozen-prediction path.  It evaluates transparent baseline/challenger methods
under the same chronological protocol and reports whether any exploratory
direction looks closer to actual outcomes than the uniform baseline.

The report is descriptive evidence only; it is not a claim that lottery draws
are predictable.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from statistics import mean, median


ALL_NUMBERS = [f"{number:03d}" for number in range(1000)]


def load_draws(db: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            "SELECT period, values_json FROM draws ORDER BY CAST(period AS INTEGER)"
        ).fetchall()
    draws: list[tuple[str, str]] = []
    for period, payload in rows:
        fields = json.loads(payload)
        number = "".join(ch for ch in str(fields[1]) if ch.isdigit())
        if len(number) == 3:
            draws.append((str(period), number))
    return draws


def uniform_scores(train: list[str]) -> dict[str, float]:
    return {number: 1.0 for number in ALL_NUMBERS}


def position_frequency_scores(train: list[str]) -> dict[str, float]:
    counts = [Counter(number[position] for number in train) for position in range(3)]
    totals = [sum(counter.values()) for counter in counts]
    scores: dict[str, float] = {}
    for number in ALL_NUMBERS:
        score = 1.0
        for position, digit in enumerate(number):
            score *= counts[position][digit] / totals[position] if totals[position] else 0.1
        scores[number] = score
    return scores


def laplace_position_frequency_scores(train: list[str], alpha: float = 1.0) -> dict[str, float]:
    counts = [Counter(number[position] for number in train) for position in range(3)]
    totals = [sum(counter.values()) for counter in counts]
    scores: dict[str, float] = {}
    for number in ALL_NUMBERS:
        score = 1.0
        for position, digit in enumerate(number):
            score *= (counts[position][digit] + alpha) / (totals[position] + 10 * alpha)
        scores[number] = score
    return scores


def recent_position_frequency_scores(train: list[str], window: int) -> dict[str, float]:
    return laplace_position_frequency_scores(train[-window:] if len(train) > window else train)


def markov_position_laplace_scores(train: list[str], alpha: float = 1.0) -> dict[str, float]:
    if len(train) < 2:
        return laplace_position_frequency_scores(train, alpha=alpha)

    transition_counts = [
        {digit: Counter() for digit in "0123456789"}
        for _ in range(3)
    ]

    for previous, current in zip(train[:-1], train[1:]):
        for position in range(3):
            transition_counts[position][previous[position]][current[position]] += 1

    last = train[-1]
    scores: dict[str, float] = {}
    for number in ALL_NUMBERS:
        score = 1.0
        for position, digit in enumerate(number):
            source_digit = last[position]
            counter = transition_counts[position][source_digit]
            total = sum(counter.values())
            score *= (counter[digit] + alpha) / (total + 10 * alpha)
        scores[number] = score
    return scores


def ranked_numbers(scores: dict[str, float]) -> list[str]:
    return sorted(ALL_NUMBERS, key=lambda number: (-scores.get(number, 0.0), number))


def evaluate_ranked_model(draws: list[tuple[str, str]], min_train: int, top_ks: list[int], scorer) -> dict:
    top_hits = {top_k: 0 for top_k in top_ks}
    ranks: list[int] = []
    recent_window = 500
    recent_top_hits = {top_k: 0 for top_k in top_ks}
    recent_ranks: list[int] = []

    for index in range(min_train, len(draws)):
        train = [number for _, number in draws[:index]]
        actual = draws[index][1]
        ranking = ranked_numbers(scorer(train))
        rank = ranking.index(actual) + 1
        ranks.append(rank)

        for top_k in top_ks:
            if rank <= top_k:
                top_hits[top_k] += 1

        if index >= len(draws) - recent_window:
            recent_ranks.append(rank)
            for top_k in top_ks:
                if rank <= top_k:
                    recent_top_hits[top_k] += 1

    tested = len(ranks)
    recent_tested = len(recent_ranks)
    mean_rank = mean(ranks) if ranks else None
    median_rank = median(ranks) if ranks else None

    result = {
        "tested": tested,
        "top_k_hit_rates": {
            str(top_k): top_hits[top_k] / tested if tested else None
            for top_k in top_ks
        },
        "mean_actual_rank": mean_rank,
        "median_actual_rank": median_rank,
        "mean_percentile": mean_rank / 1000 if mean_rank is not None else None,
        "recent_500": {
            "tested": recent_tested,
            "top_k_hit_rates": {
                str(top_k): recent_top_hits[top_k] / recent_tested if recent_tested else None
                for top_k in top_ks
            },
            "mean_actual_rank": mean(recent_ranks) if recent_ranks else None,
            "median_actual_rank": median(recent_ranks) if recent_ranks else None,
        },
    }
    return result


def model_status(model_result: dict, uniform_result: dict) -> str:
    model_top10 = model_result["top_k_hit_rates"]["10"]
    uniform_top10 = uniform_result["top_k_hit_rates"]["10"]
    model_rank = model_result["mean_actual_rank"]
    uniform_rank = uniform_result["mean_actual_rank"]

    if model_top10 is None or uniform_top10 is None or model_rank is None or uniform_rank is None:
        return "INSUFFICIENT_DATA"

    top10_edge = model_top10 - uniform_top10
    rank_edge = uniform_rank - model_rank

    if top10_edge > 0.002 and rank_edge > 10:
        return "WEAK_EXPLORATORY_SIGNAL"
    if top10_edge < -0.002 and rank_edge < -10:
        return "REJECTED_WEAK_OR_WORSE_THAN_BASELINE"
    return "NO_STABLE_ADVANTAGE_OBSERVED"


def main() -> int:
    parser = argparse.ArgumentParser(description="只读模型筛查与预测距离分析")
    base = Path(__file__).parent
    parser.add_argument("--db", type=Path, default=base / "sd3d_history.sqlite3")
    parser.add_argument("--min-train", type=int, default=500)
    parser.add_argument("--top-ks", default="10,50,100,200")
    parser.add_argument("--out", type=Path, default=base / "reports" / "model-screening-latest.json")
    args = parser.parse_args()

    top_ks = [int(value.strip()) for value in args.top_ks.split(",") if value.strip()]
    draws = load_draws(args.db)
    if len(draws) <= args.min_train:
        raise SystemExit("样本不足，无法执行模型筛查")

    model_scorers = {
        "uniform_baseline": {
            "description": "均匀基线；完整组合等分，不代表前序号码更可能。",
            "risk": "BASELINE",
            "scorer": uniform_scores,
        },
        "position_frequency": {
            "description": "全历史位置频率乘积打分。",
            "risk": "LOW_COMPLEXITY_EXPERIMENT",
            "scorer": position_frequency_scores,
        },
        "laplace_position_frequency": {
            "description": "带 Laplace 平滑的位置频率乘积打分。",
            "risk": "LOW_COMPLEXITY_EXPERIMENT",
            "scorer": laplace_position_frequency_scores,
        },
        "recent_position_frequency_50": {
            "description": "最近50期位置频率，带平滑。",
            "risk": "WINDOW_SELECTION_RISK",
            "scorer": lambda train: recent_position_frequency_scores(train, 50),
        },
        "recent_position_frequency_100": {
            "description": "最近100期位置频率，带平滑。",
            "risk": "WINDOW_SELECTION_RISK",
            "scorer": lambda train: recent_position_frequency_scores(train, 100),
        },
        "recent_position_frequency_300": {
            "description": "最近300期位置频率，带平滑。",
            "risk": "WINDOW_SELECTION_RISK",
            "scorer": lambda train: recent_position_frequency_scores(train, 300),
        },
        "markov_position_laplace": {
            "description": "分位置一阶马尔可夫转移，带 Laplace 平滑。",
            "risk": "MARKOV_ASSUMPTION_AND_OVERFIT_RISK",
            "scorer": markov_position_laplace_scores,
        },
    }

    results: dict[str, dict] = {}
    for name, spec in model_scorers.items():
        result = evaluate_ranked_model(draws, args.min_train, top_ks, spec["scorer"])
        result["description"] = spec["description"]
        result["risk"] = spec["risk"]
        results[name] = result

    uniform_result = results["uniform_baseline"]
    for name, result in results.items():
        result["delta_vs_uniform"] = {
            "top10_hit_rate": (
                result["top_k_hit_rates"]["10"] - uniform_result["top_k_hit_rates"]["10"]
                if result["top_k_hit_rates"]["10"] is not None
                else None
            ),
            "mean_rank_improvement": (
                uniform_result["mean_actual_rank"] - result["mean_actual_rank"]
                if result["mean_actual_rank"] is not None
                else None
            ),
        }
        result["status"] = "BASELINE" if name == "uniform_baseline" else model_status(result, uniform_result)

    challengers = {name: result for name, result in results.items() if name != "uniform_baseline"}
    best_by_top10 = max(
        challengers,
        key=lambda name: challengers[name]["top_k_hit_rates"]["10"],
    )
    best_by_mean_rank = min(
        challengers,
        key=lambda name: challengers[name]["mean_actual_rank"],
    )

    report = {
        "disclaimer": (
            "模型筛查是只读时间回测实验，用于发现和淘汰研究方向；"
            "不证明彩票可预测，不构成投注建议。"
        ),
        "protocol": {
            "min_train": args.min_train,
            "top_ks": top_ks,
            "tested": len(draws) - args.min_train,
            "ranking_space": 1000,
            "notes": [
                "所有模型只能使用目标期之前的数据。",
                "窗口模型存在多重比较风险，不能仅凭局部领先进入正式预测。",
                "马尔可夫模型为一阶分位置近似，不等于完整号码转移规律。"
            ],
        },
        "random_reference": {
            "expected_top_k_hit_rates": {
                str(top_k): top_k / 1000 for top_k in top_ks
            },
            "expected_mean_rank": 500.5,
        },
        "models": results,
        "summary": {
            "best_by_top10": best_by_top10,
            "best_by_mean_rank": best_by_mean_rank,
            "stable_advantage_observed": False,
            "brain_recommendation": (
                "保留为研究筛查证据；任何 challenger 进入正式冻结预测前，"
                "需要 Bootstrap、盲评和多重比较审查。"
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Model screening complete: {len(results)} models")
    print(f"Report: {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())