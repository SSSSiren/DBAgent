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
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="综合得分 0.0-1.0")
    generated_sql: str = Field(default="", description="Agent 生成的 SQL")
    reference_sql: str = Field(default="", description="参考 SQL")
    generated_row_count: Optional[int] = Field(default=None, description="生成 SQL 执行结果行数")
    reference_row_count: Optional[int] = Field(default=None, description="参考 SQL 执行结果行数")
    diff_summary: str = Field(default="", description="差异描述")
    llm_judge_explanation: Optional[str] = Field(default=None, description="Tier 3 LLM 评判解释")
    # 子维度评分（独立来源，不全部复用 score）
    syntax_ok: bool = Field(default=True, description="SQL 语法是否可执行")
    table_match: float = Field(default=0.0, ge=0.0, le=1.0, description="表名匹配度")
    column_match: float = Field(default=0.0, ge=0.0, le=1.0, description="列名匹配度")


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
    input_tokens: int = Field(default=0, description="输入 token 消耗（prompt）")
    output_tokens: int = Field(default=0, description="输出 token 消耗（completion）")
    latency_ms: int = Field(default=0, description="端到端延迟（毫秒）")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="效率综合得分")


# ========== HDC 验证 ==========

class HdcVerificationData(BaseModel):
    """HDC 上下文注入验证数据 — 对比 agent 实际使用的表名与 HDC 注入的上下文"""
    injected: bool = Field(default=False, description="本轮是否注入了 HDC 上下文")
    context_chars: int = Field(default=0, description="注入的 HDC 上下文字符数")
    reference_table: str = Field(default="", description="参考 SQL 中使用的表名")
    correct_table_in_context: bool = Field(default=False, description="参考表名是否在 HDC 上下文中出现")
    agent_table_used: str = Field(default="", description="Agent 实际使用的表名")
    agent_used_correct_table: bool = Field(default=False, description="Agent 是否使用了正确的表名")
    is_hallucination: bool = Field(default=False, description="Agent 使用的表名是否在数据库 schema 中不存在（幻觉）")


# ========== 运行时配置 ==========

class RunConfig(BaseModel):
    """评测运行时参数 — 记录在报告中便于事后追溯评测条件"""
    repeat: int = Field(default=1, description="每条用例重复执行次数")
    concurrency: int = Field(default=1, description="并发执行数")
    db_name: str = Field(default="dw_onedba", description="数据库名称")
    hdc_enabled: bool = Field(default=False, description="是否启用 HDC 数据底座")
    hdc_tables: list[str] = Field(default_factory=list, description="HDC 限定表白名单（空=全部）")
    hdc_namespace: Optional[str] = Field(default=None, description="HDC 知识库命名空间（用于变体隔离，如 incomplete/complete/overcomplete）")
    use_llm_judge: bool = Field(default=True, description="是否启用 LLM 评判（Tier 3）")
    use_quality_judge: bool = Field(default=True, description="是否启用回答质量评判")
    cli_command: Optional[str] = Field(default=None, description="完整 CLI 命令（用于复现）")


# ========== Agent 中间过程记录 ==========

class ToolCallRecord(BaseModel):
    """单次工具调用的完整记录（输入 + 输出）"""
    tool: str = Field(default="", description="工具名称")
    args: dict[str, Any] = Field(default_factory=dict, description="调用参数")
    result: str = Field(default="", description="工具返回内容（截断至 2000 字符）")


class LLMCallRecord(BaseModel):
    """单次 LLM 调用的完整输入和输出（不截断）"""
    iteration: int = Field(default=0, description="第几轮 LLM 调用（从 0 开始）")
    model: str = Field(default="", description="LLM 模型名称")
    input_messages: list[dict[str, Any]] = Field(default_factory=list, description="本轮输入 messages 列表 [{role, content}]")
    output_content: str = Field(default="", description="LLM 回复文本（完整，不截断）")
    output_tool_calls: list[dict[str, Any]] = Field(default_factory=list, description="LLM 请求的工具调用 [{name, arguments}]")
    is_final: bool = Field(default=False, description="是否为最终响应")


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
    prep_ms: float = Field(default=0.0, description="上下文准备耗时（毫秒）")
    ttfb_ms: float | None = Field(default=None, description="首个输出到达时间（毫秒）")
    tool_call_count: int = Field(default=0, description="工具调用次数")
    tool_call_details: dict[str, int] = Field(default_factory=dict, description="各工具调用次数")
    turns: int = Field(default=0, description="Agent 循环轮次")
    total_tokens: int = Field(default=0, description="Token 消耗")
    input_tokens: int = Field(default=0, description="输入 Token（prompt）")
    output_tokens: int = Field(default=0, description="输出 Token（completion）")
    generated_sqls: list[str] = Field(default_factory=list, description="生成的 SQL 列表")
    error: Optional[str] = Field(default=None, description="本次运行错误信息")
    # HDC 增强字段
    first_tool: str = Field(default="", description="Agent 第一个调用的工具名称")
    first_table_used: str = Field(default="", description="Agent 第一个查询类工具使用的表名")
    called_find_table_before_query: bool = Field(default=False, description="首次查询前是否调用了 find_table")
    # repeat 模式下的 judge 得分（可选，用于 N 次取平均）
    sql_score: Optional[float] = Field(default=None, description="本次运行的 SQL 正确性得分")
    quality_score: Optional[float] = Field(default=None, description="本次运行的 LLM 回答质量得分")


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
    std_input_tokens: float = Field(default=0.0, description="输入 Token 消耗标准差")
    std_output_tokens: float = Field(default=0.0, description="输出 Token 消耗标准差")
    std_latency_ms: float = Field(default=0.0, description="延迟标准差（毫秒）")
    std_turns: float = Field(default=0.0, description="Turns 标准差")
    # HDC 验证
    hdc_verification: Optional[HdcVerificationData] = Field(default=None, description="HDC 上下文验证数据")
    # Agent 中间过程记录
    tool_call_records: list[ToolCallRecord] = Field(default_factory=list, description="完整工具调用记录（含输入输出）")
    llm_call_records: list[LLMCallRecord] = Field(default_factory=list, description="LLM 调用记录（含提示词和回复摘要）")


# ========== 评测报告 ==========

class EvaluationReport(BaseModel):
    """顶层评测报告"""
    generated_at: datetime = Field(default_factory=datetime.now)
    schema_id: int = Field(description="测试数据库 schemaId")
    llm_model: str = Field(default="", description="使用的 LLM 模型")
    llm_base_url: str = Field(default="", description="LLM API 地址")
    total_cases: int = Field(default=0)
    total_duration_ms: int = Field(default=0, description="评测总耗时（毫秒，wall-clock）")
    run_config: Optional[RunConfig] = Field(default=None, description="运行时参数配置")
    passed_cases: int = Field(default=0)
    failed_cases: int = Field(default=0)
    error_cases: int = Field(default=0)
    overall_pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    average_score: float = Field(default=0.0, ge=0.0, le=1.0)
    average_latency_ms: float = Field(default=0.0)
    average_prep_ms: float = Field(default=0.0, description="平均上下文准备耗时")
    average_ttfb_ms: float | None = Field(default=None, description="平均 TTFB")
    average_tool_calls: float = Field(default=0.0)
    average_turns: float = Field(default=0.0)
    average_tokens: float = Field(default=0.0)
    average_input_tokens: float = Field(default=0.0, description="平均输入 Token")
    average_output_tokens: float = Field(default=0.0, description="平均输出 Token")
    std_tool_calls: float = Field(default=0.0, description="工具调用次数标准差（跨用例平均）")
    std_tokens: float = Field(default=0.0, description="Token 消耗标准差（跨用例平均）")
    std_input_tokens: float = Field(default=0.0, description="输入 Token 标准差（跨用例平均）")
    std_output_tokens: float = Field(default=0.0, description="输出 Token 标准差（跨用例平均）")
    std_latency_ms: float = Field(default=0.0, description="延迟标准差（跨用例平均）")
    std_turns: float = Field(default=0.0, description="Turns 标准差（跨用例平均）")
    dimension_averages: DimensionScores = Field(default_factory=DimensionScores)
    case_results: list[CaseResult] = Field(default_factory=list)
    baseline_comparison: Optional[dict[str, Any]] = Field(default=None, description="与基线的对比数据")
    hdc_generation_tokens: Optional[int] = Field(default=None, description="HDC 离线生成消耗的 token 数（用户通过 CLI 传入）")