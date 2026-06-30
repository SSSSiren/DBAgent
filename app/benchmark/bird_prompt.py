"""
BIRD 基准测试 - Prompt 构建模块

职责：
1. 将 BirdSchema（CSV 描述）转换为 LLM 可读的文本格式
2. 将 schema 文本 + evidence + question 拼接为 LLM prompt
3. 支持两种模式：LLM 模式（含 evidence）和 Agent 模式（不含 evidence）

与 Spider 的关键差异：
- Schema 来自 CSV 而非 JSON，包含列描述和示例值（BIRD 核心特色）
- 支持 evidence 字段（外部知识，可选）
- 支持 difficulty 字段
"""

from app.benchmark.bird_loader import BirdExample, BirdSchema


def build_schema_text_from_csv(schema: BirdSchema) -> str:
    """
    将 BirdSchema（CSV 数据）转换为 schema 描述文本

    BIRD 的 CSV 格式包含比 Spider 更丰富的信息：
    - 表描述（Description）
    - 列描述（Description）
    - 示例值（Sample Values）—— 这是 BIRD 的核心特色

    输出格式：
      Table: scores - Student test scores across subjects
        Columns:
          - student_id (INTEGER): Unique student identifier. Examples: 1001, 1002
          - math_score (INTEGER): Math test score (0-100). Examples: 85, 92
    """
    if not schema.tables and not schema.columns:
        return ""

    lines: list[str] = []

    # 构建表名→描述的映射
    table_descriptions: dict[str, str] = {}
    for t in schema.tables:
        name = t.get("Table Name", t.get("table_name", ""))
        desc = t.get("Description", t.get("description", ""))
        if name:
            table_descriptions[name] = desc

    # 按表分组列
    table_columns: dict[str, list[dict]] = {}
    for col in schema.columns:
        table_name = col.get("Table Name", col.get("table_name", ""))
        if table_name not in table_columns:
            table_columns[table_name] = []
        table_columns[table_name].append(col)

    # 生成每个表的描述
    for table_name, cols in table_columns.items():
        desc = table_descriptions.get(table_name, "")
        header = f"Table: {table_name}"
        if desc:
            header += f" — {desc}"
        lines.append(header)
        lines.append("  Columns:")

        for col in cols:
            col_name = col.get("Column Name", col.get("column_name", ""))
            col_type = col.get("Type", col.get("type", ""))
            col_desc = col.get("Description", col.get("description", ""))
            samples = col.get("Sample Values", col.get("sample_values", ""))

            parts = [f"    - {col_name}"]
            if col_type:
                parts.append(f" ({col_type})")
            if col_desc:
                parts.append(f": {col_desc}")
            if samples:
                parts.append(f" [Examples: {samples}]")

            lines.append("".join(parts))

        lines.append("")  # 空行分隔

    # 外键约束
    if schema.foreign_keys:
        lines.append("Foreign Keys:")
        for fk in schema.foreign_keys:
            table = fk.get("Table Name", fk.get("table_name", ""))
            col = fk.get("Column Name", fk.get("column_name", ""))
            ref_table = fk.get("Foreign Table Name", fk.get("foreign_table_name", ""))
            ref_col = fk.get("Foreign Column Name", fk.get("foreign_column_name", ""))
            lines.append(f"  {table}.{col} → {ref_table}.{ref_col}")

    return "\n".join(lines)


def build_prompt(
    example: BirdExample,
    include_evidence: bool = True,
) -> str:
    """
    构建 BIRD Text-to-SQL prompt

    参数：
        example: BirdExample 实例
        include_evidence: 是否包含 evidence 字段
            - True（LLM 模式）：提供 evidence 外部知识
            - False（Agent 模式）：不提供 evidence，Agent 需要自行探索

    格式（BIRD 标准）：
      Given the following database schema:
      {schema_text}

      External Knowledge:
      {evidence}

      Question: {question}
      SQL:
    """
    schema_text = build_schema_text_from_csv(example.schema)

    prompt_parts = [
        "Given the following database schema:\n",
        schema_text if schema_text else "(No schema description available)",
    ]

    if include_evidence and example.evidence:
        prompt_parts.append(f"\nExternal Knowledge:\n{example.evidence}")

    prompt_parts.append(f"\nQuestion: {example.question}")
    prompt_parts.append("\nSQL:")

    return "\n".join(prompt_parts)


def build_agent_prompt(example: BirdExample) -> str:
    """
    构建 Agent 模式的 prompt（不含 evidence 和 schema 细节）

    Agent 模式只给：
    - 数据库路径
    - 问题
    - 提示 Agent 自行探索

    Agent 需要通过工具调用自行探索 schema 和值。
    """
    return (
        f"You have access to a SQLite database at: {example.db_path}\n\n"
        f"Please answer the following question by exploring the database and writing SQL.\n\n"
        f"Question: {example.question}\n\n"
        f"Steps:\n"
        f"1. First, explore the database schema (list tables, describe columns)\n"
        f"2. Look at sample data to understand values\n"
        f"3. Write and execute the SQL query\n"
        f"4. Verify the result answers the question"
    )