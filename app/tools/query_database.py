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
        # 1. 获取表结构 - 使用 DESCRIBE 命令
        describe_sql = f"DESCRIBE {table_name}"
        describe_result = await onedba_client.execute_sql(schema_id, describe_sql)
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
        if not validation.passed:
            error_msg = "; ".join(validation.errors) if validation.errors else "SQL 验证失败"
            # 尝试修复
            repaired = await repair_sql(
                question=question,
                table_name=table_name,
                columns=columns,
                failed_sql=generated.sql,
                error_message=error_msg,
            )
            if repaired.needs_clarification or not repaired.sql:
                return f"SQL 生成失败：{error_msg}"
            generated = repaired
            validation = validate_sql(generated.sql, table_name, columns)
            if not validation.passed:
                return f"SQL 修复后仍然失败：{'; '.join(validation.errors)}"

        # 4. 执行 SQL
        result = await onedba_client.execute_sql(schema_id, generated.sql)

        # 5. 检查是否为空结果
        rows = result.get("columnDatas") or []
        is_empty = len(rows) == 0

        # 6. 格式化结果
        markdown_table = format_as_markdown_table(result)

        # 7. 构建响应 - 使用验证后的 SQL（已去除分号和多余空白）
        final_sql = validation.sql
        # 清理 SQL：去除字面的 \n 和多余空白
        final_sql = final_sql.replace('\\n', ' ').replace('\\r', '')
        final_sql = ' '.join(final_sql.split())  # 合并多个空白为单个空格

        # 打印 SQL 日志
        print(f"[query_database_tool] Generated SQL: {final_sql}")
        print(f"[query_database_tool] Result rows: {len(rows)}")

        response_parts = [
            f"## 查询结果\n",
            f"**问题**: {question}\n",
            f"**表**: {table_name}\n",
            f"**生成的 SQL**:\n```sql\n{final_sql}\n```\n",
        ]

        if generated.explanation:
            response_parts.append(f"**说明**: {generated.explanation}\n")

        if generated.assumptions:
            response_parts.append("**假设**:\n")
            for assumption in generated.assumptions:
                response_parts.append(f"- {assumption}\n")

        # 空结果时添加明确说明
        if is_empty:
            response_parts.append("\n**✅ 查询成功，结果为空**\n")
            response_parts.append("这是正常的查询结果，表示在指定条件下没有匹配的数据。")
            response_parts.append("请将此结果直接告知用户，**不要重试或修改查询**。\n")

        response_parts.append(f"\n{markdown_table}\n")

        result_text = "\n".join(response_parts)
        print(f"[query_database_tool] Full result:\n{repr(result_text)}")
        return result_text

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[query_database_tool] Error: {error_detail}")
        return f"查询执行失败：{str(e)}"
