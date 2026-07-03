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

    维度映射：
    - SQL 语法正确 (20%)：SQL Judge score
    - 表/列引用正确 (20%)：SQL Judge score（Tier 2/3 已包含列验证）
    - 过滤条件正确 (20%)：SQL Judge score
    - 结果数据正确 (30%)：SQL Judge Tier 2 结果对比（硬性要求）
    - SQL 规范 (10%)：检测无 SELECT *、有 ORDER BY、有 LIMIT
    """
    sql_score = sql_judge.score if sql_judge else 0.0

    # 前三个维度都从 SQL Judge 派生
    sql_syntax = sql_score
    table_column = sql_score
    filter_condition = sql_score

    # 结果数据正确：直接使用 SQL Judge score（Tier 2 已做结果对比）
    result_data = sql_score

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


def compute_overall_score(dimensions: DimensionScores) -> float:
    """
    计算加权总分。

    权重：
    - SQL 语法正确：20%
    - 表/列引用正确：20%
    - 过滤条件正确：20%
    - 结果数据正确：30%
    - SQL 规范：10%

    硬性约束：结果数据正确不通过（< 0.5）→ 总分上限 70%
    """
    weighted = (
        dimensions.sql_syntax * 0.20
        + dimensions.table_column * 0.20
        + dimensions.filter_condition * 0.20
        + dimensions.result_data * 0.30
        + dimensions.sql_standard * 0.10
    )

    # 硬性约束：结果数据正确不通过 → 上限 70%
    if dimensions.result_data < 0.5:
        weighted = min(weighted, 0.70)

    return round(weighted, 4)


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
    case_result.overall_score = compute_overall_score(dimensions)
    case_result.passed = case_result.overall_score >= 0.80
    return case_result