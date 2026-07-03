"""
评测框架数据模型 — 所有 Pydantic 模型定义
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ========== 测试用例 ==========

class Difficulty(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class TestCase(BaseModel):
    """从 test_cases_onedba_evaluation.md 解析出的单条测试用例"""
    case_id: str = Field(description="用例编号，如 TC-001")
    difficulty: Difficulty = Field(description="难度：Easy/Medium/Hard")
    question: str = Field(description="自然语言问题")
    reference_sql: str = Field(description="参考答案 SQL")
    expected_row_count: Optional[int] = Field(default=None, description="预期返回行数")
    category: str = Field(default="", description="分类，如 单表过滤/聚合/JOIN")
    tables: list[str] = Field(default_factory=list, description="涉及的表名")
    judging_criteria: list[str] = Field(default_factory=list, description="评判要点")


# ========== Judge 结果 ==========

class SQLJudgeResult(BaseModel):
    """SQL 正确性评判结果"""
    tier: int = Field(description="判断层级：1=结构匹配, 2=结果对比, 3=LLM评判")
    passed: bool = Field(description="是否通过")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="得分 0.0-1.0")
    generated_sql: str = Field(default="", description="Agent 生成的 SQL")
    reference_sql: str = Field(default="", description="参考 SQL")
    generated_row_count: Optional[int] = Field(default=None, description="生成 SQL 执行结果行数")
    reference_row_count: Optional[int] = Field(default=None, description="参考 SQL 执行结果行数")
    diff_summary: str = Field(default="", description="差异描述")
    llm_judge_explanation: Optional[str] = Field(default=None, description="Tier 3 LLM 评判解释")


class QualityJudgeResult(BaseModel):
    """回答质量评判结果（LLM-as-judge）"""
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="综合得分")
    completeness: float = Field(default=0.0, ge=0.0, le=1.0, description="完整性")
    accuracy: float = Field(default=0.0, ge=0.0, le=1.0, description="准确性")
    clarity: float = Field(default=0.0, ge=0.0, le=1.0, description="清晰度")
    sql_transparency: float = Field(default=0.0, ge=0.0, le=1.0, description="SQL 透明度")
    explanation: str = Field(default="", description="评判解释")


class EfficiencyMetrics(BaseModel):
    """效率指标"""
    tool_call_count: int = Field(default=0, description="工具调用总次数")
    tool_call_details: dict[str, int] = Field(default_factory=dict, description="各工具调用次数")
    turns: int = Field(default=0, description="Agent 循环轮次")
    total_tokens: int = Field(default=0, description="总 token 消耗")
    latency_ms: int = Field(default=0, description="端到端延迟（毫秒）")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="效率综合得分")


# ========== 维度评分 ==========

class DimensionScores(BaseModel):
    """5 维度评分（按测试用例中的评分标准）"""
    sql_syntax: float = Field(default=0.0, ge=0.0, le=1.0, description="SQL 语法正确 (20%)")
    table_column: float = Field(default=0.0, ge=0.0, le=1.0, description="表/列引用正确 (20%)")
    filter_condition: float = Field(default=0.0, ge=0.0, le=1.0, description="过滤条件正确 (20%)")
    result_data: float = Field(default=0.0, ge=0.0, le=1.0, description="结果数据正确 (30%)")
    sql_standard: float = Field(default=0.0, ge=0.0, le=1.0, description="SQL 规范 (10%)")


# ========== 用例结果 ==========

class RunDetail(BaseModel):
    """单次运行的效率指标（用于重复执行时收集 per-run 数据）"""
    duration_ms: int = Field(default=0, description="本次运行耗时（毫秒）")
    tool_call_count: int = Field(default=0, description="工具调用次数")
    tool_call_details: dict[str, int] = Field(default_factory=dict, description="各工具调用次数")
    turns: int = Field(default=0, description="Agent 循环轮次")
    total_tokens: int = Field(default=0, description="Token 消耗")
    generated_sqls: list[str] = Field(default_factory=list, description="生成的 SQL 列表")
    error: Optional[str] = Field(default=None, description="本次运行错误信息")


class CaseResult(BaseModel):
    """单条用例的完整评测结果"""
    test_case: TestCase
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime = Field(default_factory=datetime.now)
    duration_ms: int = Field(default=0, description="总执行时间（毫秒）")
    agent_response: str = Field(default="", description="Agent 最终回复文本")
    generated_sqls: list[str] = Field(default_factory=list, description="Agent 生成的所有 SQL")
    tool_calls: list[dict[str, Any]] = Field(default_factory=list, description="工具调用记录")
    sql_judge: Optional[SQLJudgeResult] = Field(default=None)
    quality_judge: Optional[QualityJudgeResult] = Field(default=None)
    efficiency: Optional[EfficiencyMetrics] = Field(default=None)
    dimensions: DimensionScores = Field(default_factory=DimensionScores)
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0, description="加权总分")
    passed: bool = Field(default=False, description="是否通过（>= 80%）")
    error: Optional[str] = Field(default=None, description="执行错误信息")
    # 重复执行相关字段
    repeat_count: int = Field(default=1, description="重复执行次数")
    run_details: list[RunDetail] = Field(default_factory=list, description="每次运行的详细指标")
    std_tool_calls: float = Field(default=0.0, description="工具调用次数标准差")
    std_tokens: float = Field(default=0.0, description="Token 消耗标准差")
    std_latency_ms: float = Field(default=0.0, description="延迟标准差（毫秒）")
    std_turns: float = Field(default=0.0, description="Turns 标准差")


# ========== 评测报告 ==========

class EvaluationReport(BaseModel):
    """顶层评测报告"""
    generated_at: datetime = Field(default_factory=datetime.now)
    schema_id: int = Field(description="测试数据库 schemaId")
    total_cases: int = Field(default=0)
    passed_cases: int = Field(default=0)
    failed_cases: int = Field(default=0)
    error_cases: int = Field(default=0)
    overall_pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    average_score: float = Field(default=0.0, ge=0.0, le=1.0)
    average_latency_ms: float = Field(default=0.0)
    average_tool_calls: float = Field(default=0.0)
    average_turns: float = Field(default=0.0)
    average_tokens: float = Field(default=0.0)
    std_tool_calls: float = Field(default=0.0, description="工具调用次数标准差（跨用例平均）")
    std_tokens: float = Field(default=0.0, description="Token 消耗标准差（跨用例平均）")
    std_latency_ms: float = Field(default=0.0, description="延迟标准差（跨用例平均）")
    std_turns: float = Field(default=0.0, description="Turns 标准差（跨用例平均）")
    dimension_averages: DimensionScores = Field(default_factory=DimensionScores)
    case_results: list[CaseResult] = Field(default_factory=list)
    baseline_comparison: Optional[dict[str, Any]] = Field(default=None, description="与基线的对比数据")