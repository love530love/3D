"""Small, explicit challenger-model registry for 福彩3D experiments."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    name: str
    description: str
    predict: object


def uniform(train: list[str], top_k: int) -> list[str]:
    # Deterministic representation of the uniform baseline, not a claim that
    # these first numbers are more likely than any other number.
    return [f"{n:03d}" for n in range(min(top_k, 1000))]


def position_frequency(train: list[str], top_k: int) -> list[str]:
    counts = [Counter(number[i] for number in train) for i in range(3)]
    ranked = [sorted(counter, key=lambda d: (-counter[d], d)) for counter in counts]
    return [a + b + c for a in ranked[0][:3] for b in ranked[1][:3] for c in ranked[2][:3]][:top_k]


def recent_position_frequency(train: list[str], top_k: int, window: int = 100) -> list[str]:
    return position_frequency(train[-window:], top_k)


REGISTRY = [
    ModelSpec("uniform_baseline", "均匀随机基线的确定性候选表示", uniform),
    ModelSpec("position_frequency", "训练窗口位置频率 challenger", position_frequency),
    ModelSpec("recent_position_frequency", "最近100期位置频率 challenger", recent_position_frequency),
]
