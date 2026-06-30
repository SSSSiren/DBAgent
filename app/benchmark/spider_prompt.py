"""
Spider 1.0 基准测试 - Prompt 构建模块

职责：
1. 将 SpiderSchema 转换为 CREATE TABLE 格式的文本
2. 将 schema 文本 + 问题拼接为 LLM prompt

Prompt 格式遵循 Spider 1.0 标准做法（参考 Spider1.0_使用说明.md 第 4.2 节）
"""

from app.benchmark.spider_loader import SpiderExample, SpiderSchema


def build_schema_text(schema: SpiderSchema) -> str:
    """
    将 SpiderSchema 转换为 CREATE TABLE 格式的 schema 描述文本

    输出格式：
      CREATE TABLE table1 (col1 (type), col2 (type)) PRIMARY KEY: col1
      CREATE TABLE table2 (col3 (type), col4 (type))
      FOREIGN KEY (table2.col3) REFERENCES table1(col1)

    特性：
    - 使用 table_names_original 和 column_names_original（原始名称）
    - 主键列在对应表声明后标注 PRIMARY KEY
    - 外键约束在最后单独列出
    """
    # 按表分组列
    table_columns: dict[int, list[tuple[str, str]]] = {}  # table_idx -> [(col_name, col_type), ...]
    for i, ((table_idx, col_name), col_type) in enumerate(zip(schema.column_names, schema.column_types)):
        if table_idx not in table_columns:
            table_columns[table_idx] = []
        table_columns[table_idx].append((col_name, col_type))

    # 找到每个表的主键列
    table_pks: dict[int, list[str]] = {}
    for pk_idx in schema.primary_keys:
        if pk_idx - 1 < len(schema.column_names):  # -1 因为跳过了通配符
            table_idx, col_name = schema.column_names[pk_idx - 1]
            if table_idx not in table_pks:
                table_pks[table_idx] = []
            table_pks[table_idx].append(col_name)

    lines: list[str] = []

    # 生成 CREATE TABLE 语句
    for table_idx in range(len(schema.table_names)):
        table_name = schema.table_names[table_idx]
        cols = table_columns.get(table_idx, [])
        if not cols:
            lines.append(f"CREATE TABLE {table_name} ()")
            continue

        col_strs = [f"{name} ({dtype})" for name, dtype in cols]
        line = f"CREATE TABLE {table_name} ({', '.join(col_strs)})"

        pks = table_pks.get(table_idx, [])
        if pks:
            line += f" PRIMARY KEY: {', '.join(pks)}"

        lines.append(line)

    # 生成 FOREIGN KEY 约束
    for fk in schema.foreign_keys:
        if len(fk) != 2:
            continue
        from_col_idx = fk[0] - 1  # -1 因为跳过了通配符
        to_col_idx = fk[1] - 1

        if from_col_idx < 0 or to_col_idx < 0:
            continue
        if from_col_idx >= len(schema.column_names) or to_col_idx >= len(schema.column_names):
            continue

        from_table_idx, from_col_name = schema.column_names[from_col_idx]
        to_table_idx, to_col_name = schema.column_names[to_col_idx]

        if from_table_idx >= len(schema.table_names) or to_table_idx >= len(schema.table_names):
            continue

        from_table = schema.table_names[from_table_idx]
        to_table = schema.table_names[to_table_idx]

        lines.append(f"FOREIGN KEY ({from_table}.{from_col_name}) REFERENCES {to_table}({to_col_name})")

    return "\n".join(lines)


def build_prompt(example: SpiderExample) -> str:
    """
    构建 Text-to-SQL prompt

    格式（Spider 标准）：
      Given the following database schema:
      {schema_text}

      Write a SQL query for the following question:
      Question: {question}
      SQL:
    """
    schema_text = build_schema_text(example.schema)
    return (
        f"Given the following database schema:\n\n"
        f"{schema_text}\n\n"
        f"Write a SQL query for the following question:\n\n"
        f"Question: {example.question}\n\n"
        f"SQL:"
    )