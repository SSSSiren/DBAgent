"""
query_database 工具 - 核心 NL2SQL 工具

根据用户的自然语言问题生成 SQL 并执行。
"""

from langchain_core.tools import tool
from app.nl2sql.generator import generate_sql
from app.nl2sql.repair import repair_sql
from app.nl2sql.validator import validate_sql
from app.nl2sql.schema import parse_describe_result
from app.tools.formatters import format_as_markdown_table
from app.client.onedba_client import onedba_client


@tool
async def query_database_tool(
    schema_id: int,
    question: str,
    table_name: str,
    summary: str = "",
) -> str:
    """
    自然语言查询数据库工具

    Args:
        schema_id: 数据库 schema ID
        question: 用户的自然语言问题
        table_name: 目标表名
        summary: 对话摘要（可选）

    Returns:
        Markdown 格式的查询结果
    """
    try:
        # 1. 获取表结构
        describe_result = await onedba_client.describe_table(schema_id, table_name)
        columns = parse_describe_result(describe_result)

        if not columns:
            return f"无法获取表 {table_name} 的结构信息"

        # 2. 生成 SQL
        generated = await generate_sql(
            question=question,
            table_name=table_name,
            columns=columns,
            summary=summary,
        )

        if generated.needs_clarification:
            return f"需要澄清：{generated.clarification_question}"

        if not generated.sql:
            return "无法生成 SQL，请检查问题描述"

        # 3. 验证 SQL
        validation = validate_sql(generated.sql, table_name, columns)
        if not validation.is_valid:
            # 尝试修复
            repaired = await repair_sql(
                question=question,
                table_name=table_name,
                columns=columns,
                failed_sql=generated.sql,
                error_message=validation.error_message or "SQL 验证失败",
            )
            if repaired.needs_clarification or not repaired.sql:
                return f"SQL 生成失败：{validation.error_message}"
            generated = repaired
            validation = validate_sql(generated.sql, table_name, columns)
            if not validation.is_valid:
                return f"SQL 修复后仍然失败：{validation.error_message}"

        # 4. 执行 SQL
        result = await onedba_client.execute_sql(schema_id, generated.sql)

        # 5. 格式化结果
        markdown_table = format_as_markdown_table(result)

        # 6. 构建响应
        response_parts = [
            f"## 查询结果\n",
            f"**问题**: {question}\n",
            f"**表**: {table_name}\n",
            f"**生成的 SQL**:\n```sql\n{generated.sql}\n```\n",
        ]

        if generated.explanation:
            response_parts.append(f"**说明**: {generated.explanation}\n")

        if generated.assumptions:
            response_parts.append("**假设**:\n")
            for assumption in generated.assumptions:
                response_parts.append(f"- {assumption}\n")

        response_parts.append(f"\n{markdown_table}\n")

        if validation.warnings:
            response_parts.append("\n**警告**:\n")
            for warning in validation.warnings:
                response_parts.append(f"- {warning}\n")

        return "\n".join(response_parts)

    except Exception as e:
        return f"查询执行失败：{str(e)}"
