"""
回答质量评判 — LLM-as-judge 评估 Agent 回复的完整性、准确性、清晰度、SQL 透明度
"""

from __future__ import annotations

import json
from typing import Any

from ..models import QualityJudgeResult


QUALITY_JUDGE_PROMPT = """你是一个 AI 助手回答质量评估专家。请评估以下 Agent 对数据库查询问题的回答质量。

评估维度：
1. 完整性 (completeness)：回答是否完整覆盖了用户问题的所有部分
2. 准确性 (accuracy)：回答中的事实、数据、SQL 是否正确
3. 清晰度 (clarity)：回答结构是否清晰、易读（Markdown 表格、分段等）
4. SQL 透明度 (sql_transparency)：是否展示了实际执行的 SQL 语句

每个维度 0.0-1.0 分。综合得分 = 各维度平均分。

请以 JSON 格式回复：
{"completeness": 0.0-1.0, "accuracy": 0.0-1.0, "clarity": 0.0-1.0, "sql_transparency": 0.0-1.0, "explanation": "简要评估说明"}"""


async def judge_answer_quality(
    question: str,
    agent_response: str,
    reference_sql: str,
    llm_client: Any,
) -> QualityJudgeResult:
    """
    使用 LLM 评判 Agent 回答质量。

    Args:
        question: 原始自然语言问题
        agent_response: Agent 的最终回复文本
        reference_sql: 参考 SQL（用于准确性对比）
        llm_client: OpenAI 兼容客户端

    Returns:
        QualityJudgeResult
    """
    if not agent_response:
        return QualityJudgeResult(
            score=0.0,
            completeness=0.0,
            accuracy=0.0,
            clarity=0.0,
            sql_transparency=0.0,
            explanation="Agent 未生成回复",
        )

    user_prompt = f"""用户问题：
{question}

参考 SQL：
{reference_sql}

Agent 回复：
{agent_response}

请评估以上 Agent 回复的质量。"""

    try:
        response = await llm_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": QUALITY_JUDGE_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        result = json.loads(content)

        completeness = float(result.get("completeness", 0.0))
        accuracy = float(result.get("accuracy", 0.0))
        clarity = float(result.get("clarity", 0.0))
        sql_transparency = float(result.get("sql_transparency", 0.0))

        score = (completeness + accuracy + clarity + sql_transparency) / 4

        return QualityJudgeResult(
            score=min(max(score, 0.0), 1.0),
            completeness=min(max(completeness, 0.0), 1.0),
            accuracy=min(max(accuracy, 0.0), 1.0),
            clarity=min(max(clarity, 0.0), 1.0),
            sql_transparency=min(max(sql_transparency, 0.0), 1.0),
            explanation=result.get("explanation", ""),
        )
    except Exception as e:
        return QualityJudgeResult(
            score=0.0,
            completeness=0.0,
            accuracy=0.0,
            clarity=0.0,
            sql_transparency=0.0,
            explanation=f"LLM 评判失败: {e}",
        )