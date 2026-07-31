"""
评分聚合器 — 将各 Judge 结果聚合为 5 维度评分
"""

from __future__ import annotations

import re

from .models import CaseResult, DimensionScores, SQLJudgeResult, QualityJudgeResult, EfficiencyMetrics


def _check_sql_standard(sql: str) -> float:
    """
    检查 SQL 规范性，返回 0.0-1.0 分。

    扣分项：
    - 使用 SELECT *：扣 0.4
    - 无 ORDER BY（非聚合查询）：扣 0.3
    - 无 LIMIT：扣 0.3
    """
    if not sql:
        return 0.0

    score = 1.0
    sql_upper = sql.upper()

    if "SELECT *" in sql_upper or "SELECT\n*" in sql_upper or "SELECT\r\n*" in sql_upper:
        score -= 0.4

    # 聚合查询（COUNT/SUM/AVG/MIN/MAX/GROUP BY）不强制 ORDER BY
    has_aggregate = bool(re.search(
        r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(|\bGROUP\s+BY\b",
        sql_upper,
    ))
    if not has_aggregate and "ORDER BY" not in sql_upper:
        score -= 0.3

    if "LIMIT" not in sql_upper:
        score -= 0.3

    return max(score, 0.0)


def compute_dimension_scores(
    sql_judge: SQLJudgeResult | None,
    quality_judge: QualityJudgeResult | None,
    efficiency: EfficiencyMetrics | None,
) -> DimensionScores:
    """
    将 Judge 结果聚合为 5 维度评分。

    维度映射（独立来源）：
    - SQL 语法正确 (10%)：SQL 是否可执行（syntax_ok → 1.0/0.0）
    - 表/列引用正确 (10%)：table_match 与 column_match 平均
    - 过滤条件正确 (10%)：从 SQL Judge score 中扣除表/列影响后的语义分
    - 结果数据正确 (60%)：Tier 2 结果对比（行数+数据匹配）
    - SQL 规范 (10%)：检测无 SELECT *、有 ORDER BY、有 LIMIT
    """
    if not sql_judge:
        return DimensionScores()

    # SQL 语法正确：是否执行成功
    sql_syntax = 1.0 if sql_judge.syntax_ok else 0.0

    # 表/列引用正确：表名匹配 + 列名匹配
    table_column = (sql_judge.table_match + sql_judge.column_match) / 2

    # 过滤条件正确：当表和列都对但结果仍不匹配时，问题在过滤条件
    # 用 SQL Judge score 扣除表/列影响后的值
    filter_condition = max(0.0, sql_judge.score - (1.0 - table_column) * 0.5)

    # 结果数据正确：直接用 SQL Judge score（Tier 2 已有行数/数据对比）
    result_data = sql_judge.score

    # SQL 规范
    generated_sql = sql_judge.generated_sql if sql_judge else ""
    sql_standard = _check_sql_standard(generated_sql)

    return DimensionScores(
        sql_syntax=sql_syntax,
        table_column=table_column,
        filter_condition=filter_condition,
        result_data=result_data,
        sql_standard=sql_standard,
    )


def compute_overall_score(dimensions: DimensionScores, quality_score: float | None = None) -> float:
    """
    计算加权总分。

    SQL 维度权重（80%）：
    - SQL 语法正确：10%
    - 表/列引用正确：10%
    - 过滤条件正确：10%
    - 结果数据正确：60%
    - SQL 规范：10%

    回答质量维度权重（20%，可选）：
    - quality_score：来自 QualityJudge 的综合评分（completeness/accuracy/clarity/sql_transparency 平均）

    总分 = 0.80 × sql_weighted + 0.20 × quality_score（有 quality_judge 时）
    总分 = sql_weighted（无 quality_judge 时，如 --no-quality-judge）

    硬性约束：result_data < 0.5 → sql_weighted 上限 70%
    """
    sql_weighted = (
        dimensions.sql_syntax * 0.10
        + dimensions.table_column * 0.10
        + dimensions.filter_condition * 0.10
        + dimensions.result_data * 0.60
        + dimensions.sql_standard * 0.10
    )

    # 硬性约束：结果数据正确不通过 → SQL 部分上限 70%
    if dimensions.result_data < 0.5:
        sql_weighted = min(sql_weighted, 0.70)

    if quality_score is not None:
        # 融合质量评分：80% SQL + 20% 回答质量
        return round(0.80 * sql_weighted + 0.20 * quality_score, 4)

    return round(sql_weighted, 4)


def score_case(case_result: CaseResult) -> CaseResult:
    """
    对单条用例结果进行评分。

    修改 case_result 的 dimensions 和 overall_score 字段。
    """
    dimensions = compute_dimension_scores(
        case_result.sql_judge,
        case_result.quality_judge,
        case_result.efficiency,
    )
    case_result.dimensions = dimensions

    # 提取 quality_score（来自 QualityJudge），传入 overall 计算
    quality_score: float | None = None
    if case_result.quality_judge is not None:
        quality_score = case_result.quality_judge.score

    case_result.overall_score = compute_overall_score(dimensions, quality_score)
    case_result.passed = case_result.overall_score >= 0.80
    return case_result