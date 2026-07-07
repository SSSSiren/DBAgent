"""
SQL 正确性评判 — 3 层判断：结构匹配 → 结果对比 → LLM 评判
"""

from __future__ import annotations

import math
import re
from typing import Any

from ..models import SQLJudgeResult


# 公平比对：参考 SQL 也追加同样的安全 LIMIT，消除行数不一致的系统性偏差
_JUDGE_SAFETY_LIMIT = 500


def _strip_limit(sql: str) -> str:
    """去除 SQL 末尾的 LIMIT 子句和分号"""
    sql = re.sub(r"\s+LIMIT\s+\d+(\s*;?\s*)$", "", sql, flags=re.IGNORECASE)
    return sql.rstrip(";").strip()


def _safe_get_list(result: dict[str, Any] | None, key: str) -> list[Any]:
    """安全获取 list 字段，处理 key 不存在或值为 None 的情况"""
    if not result:
        return []
    val = result.get(key)
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return []


def _extract_table_names(sql: str) -> set[str]:
    """从 SQL 中提取表名（FROM/JOIN 后的标识符）"""
    import re
    sql_upper = sql.upper()
    tables: set[str] = set()
    for match in re.finditer(
        r'\b(?:FROM|JOIN)\s+`?(\w+)`?',
        sql_upper,
    ):
        tables.add(match.group(1).lower())
    return tables


def _extract_column_names(sql: str) -> set[str]:
    """从 SQL 中提取列名（SELECT 后的标识符，不含聚合函数参数）"""
    import re
    # 提取 SELECT 和 FROM 之间的部分
    match = re.search(r'\bSELECT\b(.*?)\bFROM\b', sql, re.DOTALL | re.IGNORECASE)
    if not match:
        return set()
    select_part = match.group(1)
    columns: set[str] = set()
    # 匹配列名：字母开头，可能含下划线，前面不是函数的括号
    for m in re.finditer(r'(?<!\w)([a-zA-Z_][a-zA-Z0-9_]*)', select_part):
        col = m.group(1).lower()
        # 排除 SQL 关键字和聚合函数
        if col not in {'count', 'sum', 'avg', 'min', 'max', 'as', 'distinct', 'all', 'null', 'true', 'false', 'limit', 'order', 'group', 'by', 'having', 'where', 'and', 'or', 'not', 'in', 'is', 'like', 'between'}:
            columns.add(col)
    return columns


def _compute_overlap(gen_set: set[str], ref_set: set[str]) -> float:
    """计算两个集合的重叠度"""
    if not ref_set:
        return 0.0
    return len(gen_set & ref_set) / len(ref_set) if ref_set else 0.0


def _normalize_sql(sql: str) -> str:
    """规范化 SQL 字符串用于结构匹配"""
    sql = re.sub(r"\s+", " ", sql.strip()).lower()
    sql = sql.rstrip(";").strip()
    sql = re.sub(r"\blimit\s+(\d+)", r"limit \1", sql)
    return sql
    """规范化 SQL 字符串用于结构匹配"""
    sql = re.sub(r"\s+", " ", sql.strip()).lower()
    sql = sql.rstrip(";").strip()
    sql = re.sub(r"\blimit\s+(\d+)", r"limit \1", sql)
    return sql


def _compare_results(
    gen_result: dict[str, Any],
    ref_result: dict[str, Any],
) -> tuple[bool, str]:
    """比较两个 OneDBA 执行结果"""
    gen_datas = _safe_get_list(gen_result, "columnDatas")
    ref_datas = _safe_get_list(ref_result, "columnDatas")

    gen_cols = _normalize_column_names(_safe_get_list(gen_result, "columnNames"))
    ref_cols = _normalize_column_names(_safe_get_list(ref_result, "columnNames"))

    gen_row_count = len(gen_datas)
    ref_row_count = len(ref_datas)

    if gen_row_count != ref_row_count:
        return False, f"行数不一致：生成={gen_row_count}, 参考={ref_row_count}"

    if set(gen_cols) != set(ref_cols):
        only_gen = set(gen_cols) - set(ref_cols)
        only_ref = set(ref_cols) - set(gen_cols)
        parts = []
        if only_gen:
            parts.append(f"仅生成结果有: {only_gen}")
        if only_ref:
            parts.append(f"仅参考结果有: {only_ref}")
        return False, "; ".join(parts)

    gen_rows = _rows_to_sorted_tuples(gen_datas, gen_cols, ref_cols)
    ref_rows = _rows_to_sorted_tuples(ref_datas, ref_cols, ref_cols)

    if gen_rows != ref_rows:
        diff_count = len(gen_rows.symmetric_difference(ref_rows))
        return False, f"数据内容不一致：{diff_count} 行不匹配"

    return True, "结果完全一致"


def _normalize_column_names(column_names: list[Any]) -> list[str]:
    """从 OneDBA columnNames 中提取列名列表"""
    result: list[str] = []
    for c in column_names:
        if isinstance(c, dict):
            result.append(c.get("key", c.get("title", "")))
    return result


def _rows_to_sorted_tuples(
    rows: list[dict[str, Any]],
    actual_cols: list[str],
    target_cols: list[str],
) -> set[tuple[Any, ...]]:
    """将行数据转为排序后的 tuple 集合"""
    result: set[tuple[Any, ...]] = set()
    for row in rows:
        tup = tuple(
            _normalize_value(row.get(col))
            for col in target_cols
        )
        result.add(tup)
    return result


def _normalize_value(val: Any) -> Any:
    """归一化值用于比较：处理 None、浮点数精度"""
    if val is None:
        return "__NULL__"
    if isinstance(val, float):
        if math.isnan(val):
            return "__NAN__"
        return round(val, 6)
    if isinstance(val, (int, bool)):
        return val
    return str(val)


def _compute_partial_score(
    gen_row_count: int,
    ref_row_count: int,
    gen_cols: list[str],
    ref_cols: list[str],
) -> float:
    """根据行数和列的重叠度计算部分分"""
    if ref_row_count > 0:
        row_score = min(gen_row_count, ref_row_count) / max(gen_row_count, ref_row_count)
    else:
        row_score = 1.0 if gen_row_count == 0 else 0.0

    gen_set = set(gen_cols)
    ref_set = set(ref_cols)
    if ref_set:
        col_score = len(gen_set & ref_set) / len(ref_set)
    else:
        col_score = 1.0

    return (row_score + col_score) / 2


async def judge_sql_correctness(
    generated_sql: str,
    reference_sql: str,
    schema_id: int,
    question: str,
    onedba_client: Any,
    llm_client: Any = None,
) -> SQLJudgeResult:
    """
    3 层 SQL 正确性评判。
    Tier 1: 结构匹配（字符串规范化后一致）
    Tier 2: 结果对比（在真实数据库上执行两条 SQL 并比较结果）
    Tier 3: LLM 评判（语义等价性判断）
    """
    if not generated_sql:
        return SQLJudgeResult(
            tier=0, passed=False, score=0.0,
            generated_sql="", reference_sql=reference_sql,
            diff_summary="Agent 未生成 SQL",
            syntax_ok=False, table_match=0.0, column_match=0.0,
        )

    # 计算子维度（在 Tier 2 之前统一计算一次）
    gen_tables = _extract_table_names(generated_sql)
    ref_tables = _extract_table_names(reference_sql)
    gen_cols_set = _extract_column_names(generated_sql)
    ref_cols_set = _extract_column_names(reference_sql)
    table_match = _compute_overlap(gen_tables, ref_tables)
    column_match = _compute_overlap(gen_cols_set, ref_cols_set)

    # Tier 1: 结构匹配
    norm_gen = _normalize_sql(generated_sql)
    norm_ref = _normalize_sql(reference_sql)
    if norm_gen == norm_ref:
        return SQLJudgeResult(
            tier=1, passed=True, score=1.0,
            generated_sql=generated_sql, reference_sql=reference_sql,
            diff_summary="SQL 结构与参考完全一致",
            syntax_ok=True, table_match=1.0, column_match=1.0,
        )

    # Tier 2: 结果对比
    # 统一剥离 LIMIT 并追加相同安全 LIMIT，消除"参考无 LIMIT vs 生成有 LIMIT"的系统性偏差
    gen_sql_for_exec = f"{_strip_limit(generated_sql)} LIMIT {_JUDGE_SAFETY_LIMIT}"
    ref_sql_for_exec = f"{_strip_limit(reference_sql)} LIMIT {_JUDGE_SAFETY_LIMIT}"

    gen_result = None
    ref_result = None
    gen_error = None
    ref_error = None

    try:
        gen_result = await onedba_client.execute_sql(schema_id=schema_id, sql=gen_sql_for_exec)
    except Exception as e:
        gen_error = str(e)

    try:
        ref_result = await onedba_client.execute_sql(schema_id=schema_id, sql=ref_sql_for_exec)
    except Exception as e:
        ref_error = str(e)

    gen_datas = _safe_get_list(gen_result, "columnDatas")
    ref_datas = _safe_get_list(ref_result, "columnDatas")
    gen_row_count = len(gen_datas)
    ref_row_count = len(ref_datas)

    gen_cols = _normalize_column_names(_safe_get_list(gen_result, "columnNames"))
    ref_cols = _normalize_column_names(_safe_get_list(ref_result, "columnNames"))

    # 任一 SQL 执行失败 → 进入 Tier 3
    if gen_error or ref_error:
        partial_score = 0.0
        diff_parts = []
        if gen_error:
            diff_parts.append(f"生成 SQL 执行失败: {gen_error}")
        if ref_error:
            diff_parts.append(f"参考 SQL 执行失败: {ref_error}")

        if llm_client:
            return await _llm_judge(
                generated_sql, reference_sql, question,
                gen_result, ref_result, gen_error, ref_error,
                "; ".join(diff_parts), partial_score, llm_client,
                table_match, column_match,
            )
        return SQLJudgeResult(
            tier=2, passed=False, score=partial_score,
            generated_sql=generated_sql, reference_sql=reference_sql,
            generated_row_count=gen_row_count, reference_row_count=ref_row_count,
            diff_summary="; ".join(diff_parts),
            syntax_ok=False, table_match=table_match, column_match=column_match,
        )

    # 结果对比
    match, diff_desc = _compare_results(gen_result, ref_result)

    if match:
        return SQLJudgeResult(
            tier=2, passed=True, score=1.0,
            generated_sql=generated_sql, reference_sql=reference_sql,
            generated_row_count=gen_row_count, reference_row_count=ref_row_count,
            diff_summary="结果数据完全一致",
            syntax_ok=True, table_match=1.0, column_match=1.0,
        )

    # 结果不一致，计算部分分
    partial_score = _compute_partial_score(gen_row_count, ref_row_count, gen_cols, ref_cols)

    if llm_client:
        return await _llm_judge(
            generated_sql, reference_sql, question,
            gen_result, ref_result, None, None,
            diff_desc, partial_score, llm_client,
            table_match, column_match,
        )

    return SQLJudgeResult(
        tier=2, passed=False, score=partial_score,
        generated_sql=generated_sql, reference_sql=reference_sql,
        generated_row_count=gen_row_count, reference_row_count=ref_row_count,
        diff_summary=diff_desc,
        syntax_ok=True, table_match=table_match, column_match=column_match,
    )


async def _llm_judge(
    generated_sql: str,
    reference_sql: str,
    question: str,
    gen_result: dict[str, Any] | None,
    ref_result: dict[str, Any] | None,
    gen_error: str | None,
    ref_error: str | None,
    diff_desc: str,
    partial_score: float,
    llm_client: Any,
    table_match: float = 0.0,
    column_match: float = 0.0,
) -> SQLJudgeResult:
    """Tier 3: 使用 LLM 判断语义等价性"""
    import json

    def _preview(result: dict[str, Any] | None, max_rows: int = 10) -> str:
        if result is None:
            return "执行失败"
        datas = _safe_get_list(result, "columnDatas")
        names = _normalize_column_names(_safe_get_list(result, "columnNames"))
        preview = datas[:max_rows]
        return f"列: {names}\n前{len(preview)}行: {json.dumps(preview, ensure_ascii=False, default=str)}"

    gen_preview = _preview(gen_result) if not gen_error else f"执行失败: {gen_error}"
    ref_preview = _preview(ref_result) if not ref_error else f"执行失败: {ref_error}"

    gen_row_count = len(_safe_get_list(gen_result, "columnDatas")) if gen_result else None
    ref_row_count = len(_safe_get_list(ref_result, "columnDatas")) if ref_result else None

    prompt = f"""你是一个 SQL 专家。请判断两个 SQL 查询在语义上是否等价。

原始问题：{question}

参考 SQL：
{reference_sql}
参考结果：{ref_preview}

生成 SQL：
{generated_sql}
生成结果：{gen_preview}

差异描述：{diff_desc}

请以 JSON 格式回复：
{{"equivalent": true/false, "score": 0.0-1.0, "explanation": "简要说明是否等价及原因"}}

注意：
- score 应反映语义等价程度（1.0=完全等价，0.0=完全不等价）
- 如果两个 SQL 查询返回的数据在业务含义上一致，即使 SQL 写法不同，也应视为等价
- 如果生成 SQL 的查询结果能正确回答原始问题，即使与参考结果不同，也应给予较高分数"""

    try:
        response = await llm_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个精确的 SQL 语义分析专家。只回复 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        result = json.loads(content)

        equivalent = result.get("equivalent", False)
        llm_score = float(result.get("score", partial_score))
        explanation = result.get("explanation", "")

        return SQLJudgeResult(
            tier=3,
            passed=equivalent and llm_score >= 0.8,
            score=max(llm_score, partial_score),
            generated_sql=generated_sql,
            reference_sql=reference_sql,
            generated_row_count=gen_row_count,
            reference_row_count=ref_row_count,
            diff_summary=diff_desc,
            llm_judge_explanation=explanation,
            syntax_ok=True, table_match=table_match, column_match=column_match,
        )
    except Exception as e:
        return SQLJudgeResult(
            tier=3, passed=False, score=partial_score,
            generated_sql=generated_sql, reference_sql=reference_sql,
            diff_summary=f"{diff_desc} (LLM 评判失败: {e})",
            syntax_ok=False, table_match=table_match, column_match=column_match,
        )