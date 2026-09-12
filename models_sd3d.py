"""Small, explicit challenger-model registry for 福彩3D experiments.

v1.1: expanded with a multi-family challenger battery. The five additional
challengers are adapter-wrapped scorers from `model_screening`, so they share
the same chronological protocol while conforming to the REGISTRY `predict`
contract. Each ModelSpec also carries an optional `distribution` callable used
by `probability_metrics` to compute per-position log-loss / Brier under one
common framework.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from model_screening import (
    ALL_NUMBERS,
    laplace_position_frequency_scores,
    markov_position_laplace_scores,
    recent_position_frequency_scores,
    ranked_numbers,
)


@dataclass(frozen=True)
class ModelSpec:
    name: str
    description: str
    predict: object
    distribution: object = None  # (train, position, alpha) -> list[float] length 10, sums to ~1


def uniform(train: list[str], top_k: int) -> list[str]:
    # Deterministic representation of the uniform baseline, not a claim that
    # these first numbers are more likely than any other number.
    return [f"{n:03d}" for n in range(min(top_k, 1000))]


def uniform_distribution(train: list[str], position: int, alpha: float) -> list[float]:
    return [0.1] * 10


def _smoothed(train: list[str], position: int, alpha: float) -> list[float]:
    counts = Counter(number[position] for number in train)
    denominator = len(train) + 10 * alpha
    return [(counts[str(digit)] + alpha) / denominator for digit in range(10)]


def position_frequency(train: list[str], top_k: int) -> list[str]:
    counts = [Counter(number[i] for number in train) for i in range(3)]
    ranked = [sorted(counter, key=lambda d: (-counter[d], d)) for counter in counts]
    return [a + b + c for a in ranked[0][:3] for b in ranked[1][:3] for c in ranked[2][:3]][:top_k]


def position_frequency_distribution(train: list[str], position: int, alpha: float) -> list[float]:
    return _smoothed(train, position, alpha)


def recent_position_frequency(train: list[str], top_k: int, window: int = 100) -> list[str]:
    return position_frequency(train[-window:], top_k)


def recent_position_frequency_distribution(train: list[str], position: int, alpha: float, window: int = 100) -> list[float]:
    return _smoothed(train[-window:], position, alpha)


def screening_adapter(name: str, description: str, scorer) -> ModelSpec:
    """Wrap a model_screening scorer into a REGISTRY ModelSpec.

    predict() returns the top_k numbers by the scorer's joint ranking;
    distribution() marginalizes the joint score into a per-position probability
    so probability_metrics can score it under the same log-loss framework.
    """
    def predict(train: list[str], top_k: int) -> list[str]:
        return ranked_numbers(scorer(train))[:top_k]

    def distribution(train: list[str], position: int, alpha: float) -> list[float]:
        scores = scorer(train)
        total = sum(scores.values()) or 1.0
        return [
            sum(scores[n] for n in ALL_NUMBERS if n[position] == str(digit)) / total
            for digit in range(10)
        ]

    return ModelSpec(name, description, predict, distribution)


REGISTRY = [
    ModelSpec("uniform_baseline", "均匀随机基线的确定性候选表示", uniform, uniform_distribution),
    ModelSpec("position_frequency", "训练窗口位置频率 challenger", position_frequency, position_frequency_distribution),
    ModelSpec(
        "recent_position_frequency",
        "最近100期位置频率 challenger",
        recent_position_frequency,
        lambda train, position, alpha: recent_position_frequency_distribution(train, position, alpha, 100),
    ),
    # --- v1.1 multi-family battery (adapter-wrapped from model_screening) ---
    screening_adapter(
        "laplace_position_frequency",
        "带 Laplace 平滑的位置频率乘积打分",
        laplace_position_frequency_scores,
    ),
    screening_adapter(
        "recent_position_frequency_50",
        "最近50期位置频率，带平滑",
        lambda train: recent_position_frequency_scores(train, 50),
    ),
    screening_adapter(
        "recent_position_frequency_100",
        "最近100期位置频率，带平滑",
        lambda train: recent_position_frequency_scores(train, 100),
    ),
    screening_adapter(
        "recent_position_frequency_300",
        "最近300期位置频率，带平滑",
        lambda train: recent_position_frequency_scores(train, 300),
    ),
    screening_adapter(
        "markov_position_laplace",
        "分位置一阶马尔可夫转移，带 Laplace 平滑",
        markov_position_laplace_scores,
    ),
]
