"""
效率评判 — 纯算法评分，不依赖 LLM

从 Agent 执行过程中收集的指标：
- tool_call_count：工具调用总次数
- turns：Agent 循环轮次
- total_tokens：总 token 消耗
- latency_ms：端到端延迟

按可配置阈值归一化到 0-1 分。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import EfficiencyMetrics


@dataclass
class EfficiencyThresholds:
    """效率阈值配置"""
    max_tool_calls: int = 25       # 超过此值计 0 分
    max_turns: int = 20            # 超过此值计 0 分
    max_tokens: int = 500000       # 超过此值计 0 分
    max_latency_ms: int = 240_000  # 超过此值计 0 分（240 秒）


def _linear_score(value: float, max_value: float) -> float:
    """线性归一化：value 越小分数越高，超过 max_value 得 0 分"""
    if value <= 0:
        return 1.0
    if value >= max_value:
        return 0.0
    return max(0.0, 1.0 - (value / max_value))


def compute_efficiency_metrics(
    tool_call_count: int,
    tool_call_details: dict[str, int],
    turns: int,
    total_tokens: int,
    latency_ms: int,
    thresholds: EfficiencyThresholds | None = None,
) -> EfficiencyMetrics:
    """
    计算效率指标和综合得分。

    Args:
        tool_call_count: 工具调用总次数
        tool_call_details: 各工具调用次数分布
        turns: Agent 循环轮次
        total_tokens: 总 token 消耗
        latency_ms: 端到端延迟（毫秒）
        thresholds: 阈值配置，None 使用默认值

    Returns:
        EfficiencyMetrics
    """
    if thresholds is None:
        thresholds = EfficiencyThresholds()

    tool_score = _linear_score(tool_call_count, thresholds.max_tool_calls)
    turn_score = _linear_score(turns, thresholds.max_turns)
    token_score = _linear_score(total_tokens, thresholds.max_tokens)
    latency_score = _linear_score(latency_ms, thresholds.max_latency_ms)

    # 综合得分：各维度平均
    overall_score = (tool_score + turn_score + token_score + latency_score) / 4

    return EfficiencyMetrics(
        tool_call_count=tool_call_count,
        tool_call_details=tool_call_details,
        turns=turns,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        score=round(overall_score, 4),
    )


def compute_efficiency_from_stats(
    stats: dict[str, Any],
    tool_call_count: int,
    tool_call_details: dict[str, int],
    thresholds: EfficiencyThresholds | None = None,
) -> EfficiencyMetrics:
    """
    从 Agent stats 字典和工具调用记录计算效率指标。

    Args:
        stats: 来自 run_agent_stream final 事件的 stats 字典
        tool_call_count: 实际工具调用次数
        tool_call_details: 各工具调用次数分布
        thresholds: 阈值配置

    Returns:
        EfficiencyMetrics
    """
    turns = stats.get("num_turns", 0)
    if isinstance(turns, dict):
        # 有时 SDK 返回的 num_turns 是 dict
        turns = turns.get("value", 0) if isinstance(turns, dict) else 0

    total_tokens = stats.get("tokens", 0)
    latency_ms = stats.get("duration_ms", 0)

    return compute_efficiency_metrics(
        tool_call_count=int(tool_call_count),
        tool_call_details=tool_call_details,
        turns=int(turns),
        total_tokens=int(total_tokens) if total_tokens else 0,
        latency_ms=int(latency_ms) if latency_ms else 0,
        thresholds=thresholds,
    )