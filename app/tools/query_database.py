"""
query_database 工具 — NL2SQL 核心工具

将自然语言问题转换为 SQL 并执行，是 DBAgent 最核心的能力。

流程：
1. DESCRIBE 表 → 获取表结构
2. 加载语义规则
3. LLM 生成 SQL
4. 验证 SQL（安全检查、字段检查）
5. 失败时 LLM 修复（最多 1 次重试）
6. 执行 COUNT 获取真实总数
7. 执行 SQL（带 LIMIT 防止拉爆）
8. 格式化结果（Markdown 表格 + SQL + 说明 + 真实总数）

参考 DBAgent 的 app/tools/query_database.py
"""

import re

from app.client.onedba import get_onedba_client
from app.nl2sql.generator import generate_sql
from app.nl2sql.repair import repair_sql
from app.nl2sql.validator import validate_sql
from app.nl2sql.schema import parse_describe_result
from app.tools.formatters import format_as_markdown_table
from app.tools.sql_utils import strip_limit, to_count_sql


DEFAULT_SAFETY_LIMIT = 500  # 工程安全 LIMIT，防止一次性返回太多数据挤爆 LLM 上下文


async def query_database(
    schema_id: int,
    question: str,
    table_name: str,
    summary: str = "",
) -> str:
    """
    自然语言查询数据库。根据用户问题生成 SQL 并执行。

    参数:
        schema_id: 数据库 schema ID（必需）
        question: 用户的自然语言问题（必需）
        table_name: 目标表名（必需）
        summary: 对话摘要（可选），用于理解上下文

    返回:
        Markdown 格式的查询结果，包含：
        - 生成的 SQL 语句
        - 查询说明和假设
        - 真实总行数（含 LIMIT 时先 COUNT）
        - 结果表格

    使用场景:
        - 用户用自然语言描述查询需求（如"查一下最近 30 天的订单数"）
        - 追问和修改查询（Agent 会重新调用此工具并传入完整问题）
    """

    client = get_onedba_client()

    try:
        # 1. DESCRIBE table(s) → 获取表结构
        # 支持逗号分隔的多表名（如 "db_alert_current, db_instance"），
        # 逐表 DESCRIBE 后合并 columns，给每列加上表名前缀避免歧义。
        table_names = [t.strip() for t in table_name.split(",") if t.strip()]
        all_columns: list[Any] = []

        for t_name in table_names:
            describe_sql = f"DESCRIBE {t_name}"
            describe_result = await client.execute_sql(schema_id, describe_sql)
            columns = parse_describe_result(describe_result)

            if not columns:
                return f"无法获取表 {t_name} 的结构信息"

            # 给每列的 name 加上表名前缀，帮助 LLM 区分同名字段
            for col in columns:
                col.name = f"{t_name}.{col.name}"
            all_columns.extend(columns)

        if not all_columns:
            return f"无法获取表 {table_name} 的结构信息"

        # 2. 生成 SQL
        generated = await generate_sql(
            question=question,
            table_name=table_name,
            columns=all_columns,
            summary=summary,
        )

        if generated.needs_clarification:
            return f"需要澄清：{generated.clarification_question}"

        if not generated.sql:
            return "无法生成 SQL，请检查问题描述"

        # 3. 验证 SQL
        validation = validate_sql(generated.sql, table_name, all_columns)
        if not validation.passed:
            error_msg = (
                "; ".join(validation.errors)
                if validation.errors
                else "SQL 验证失败"
            )
            # 4. 尝试修复（最多 1 次重试）
            repaired = await repair_sql(
                question=question,
                table_name=table_name,
                columns=all_columns,
                failed_sql=generated.sql,
                error_message=error_msg,
            )
            if repaired.needs_clarification or not repaired.sql:
                return f"SQL 生成失败：{error_msg}"
            generated = repaired
            validation = validate_sql(generated.sql, table_name, all_columns)
            if not validation.passed:
                return (
                    f"SQL 修复后仍然失败："
                    f"{'; '.join(validation.errors)}"
                )

        final_sql = validation.sql

        # 5. 工程层处理：根据 LLM 的 has_topn 二分类结果决定是否保留 SQL 中的 LIMIT
        #
        # 设计意图：
        # - LLM 做二分类：has_topn=true 表示用户明确要求了 TopN（如"前10条"）
        # - has_topn=true：信任 LLM 在 SQL 中写的 LIMIT N（自然语言→SQL 翻译是 LLM 的强项）
        # - has_topn=false：剥离 LLM 习惯性加的 LIMIT（不可靠），执行时加安全 LIMIT 500（防 OOM，不展示）
        # - 先 COUNT 获取真实总数，告知用户当前返回量与真实总量的关系
        #
        total_count: int | None = None

        # 5a. 剥离 LLM 可能残留的 LIMIT（不可靠），执行 COUNT 获取真实总数
        clean_sql = strip_limit(final_sql)
        count_sql = to_count_sql(clean_sql)
        try:
            count_result = await client.execute_sql(schema_id, count_sql)
            count_rows = count_result.get("columnDatas") or []
            if count_rows:
                raw = count_rows[0].get("cnt")
                if raw is not None:
                    total_count = int(raw)
        except Exception:
            total_count = None

        # 5b. 根据 has_topn 决定 display_sql 和 execute_sql
        if generated.has_topn:
            # 用户有明确 TopN 意图 → 保留 LLM 在 SQL 中写的 LIMIT N
            # 注意：LLM 的 SQL 已通过 validate_sql 的 strip_sql 规范化，LIMIT 数字可靠
            display_sql = final_sql
            execute_sql_str = final_sql
            # 从 SQL 中提取 LIMIT 值用作展示
            limit_match = re.search(r"\bLIMIT\s+(\d+)\b", final_sql, re.IGNORECASE)
            applied_limit = int(limit_match.group(1)) if limit_match else DEFAULT_SAFETY_LIMIT
        else:
            # 无 TopN 意图 → 最终 SQL 干净（无 LIMIT），执行时安全兜底
            display_sql = clean_sql
            execute_sql_str = f"{clean_sql} LIMIT {DEFAULT_SAFETY_LIMIT}"
            applied_limit = DEFAULT_SAFETY_LIMIT

        # 6. 执行 SQL
        result = await client.execute_sql(schema_id, execute_sql_str)

        # 7. 检查是否为空结果
        rows = result.get("columnDatas") or []
        is_empty = len(rows) == 0

        # 8. 格式化结果
        markdown_table = format_as_markdown_table(result)

        # 清理 SQL 显示
        display_sql = display_sql.replace("\\n", " ").replace("\\r", "")
        display_sql = " ".join(display_sql.split())

        # 日志
        print(f"[query_database] Generated SQL: {display_sql}")
        print(f"[query_database] Result rows: {len(rows)}")
        if total_count is not None:
            print(f"[query_database] Total count: {total_count}")

        # 9. 构建响应
        response_parts = [
            "## 查询结果\n",
            f"**问题**: {question}\n",
            f"**表**: {table_name}\n",
            f"**生成的 SQL**:\n```sql\n{display_sql}\n```\n",
        ]

        if generated.explanation:
            response_parts.append(f"**说明**: {generated.explanation}\n")

        if generated.assumptions:
            response_parts.append("**假设**:\n")
            for assumption in generated.assumptions:
                response_parts.append(f"- {assumption}\n")

        # 真实总数
        if total_count is not None and not generated.has_topn:
            response_parts.append(
                f"\n**真实总数**: {total_count} 条"
                f"（系统自动限制显示前 {applied_limit} 条，防止数据量过大）\n"
            )
        elif total_count is not None:
            response_parts.append(
                f"\n**真实总数**: {total_count} 条"
                f"（按用户要求显示前 {applied_limit} 条）\n"
            )

        # 空结果说明
        if is_empty:
            response_parts.append("\n**✅ 查询成功，结果为空**\n")
            response_parts.append(
                "这是正常的查询结果，表示在指定条件下没有匹配的数据。"
            )
            response_parts.append(
                "请将此结果直接告知用户，**不要重试或修改查询**。\n"
            )

        response_parts.append(f"\n{markdown_table}\n")

        return "\n".join(response_parts)

    except Exception as e:
        import traceback

        error_detail = traceback.format_exc()
        print(f"[query_database] Error: {error_detail}")
        return f"查询执行失败：{str(e)}"