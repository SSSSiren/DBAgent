"""
Spider 1.0 基准测试 - 数据加载模块

职责：
1. 解析 Spider 数据格式（dev.json / train_spider.json / tables.json）
2. 将原始数据转换为结构化的 SpiderExample / SpiderSchema
3. 按 db_id 匹配问题和数据库 schema
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SpiderSchema:
    """Spider 数据库 Schema 定义"""
    db_id: str
    table_names: list[str]              # table_names_original
    column_names: list[tuple[int, str]]  # (table_index, column_name)，不含通配符 [-1, "*"]
    column_types: list[str]
    primary_keys: list[int]
    foreign_keys: list[tuple[int, int]]  # [(from_col_idx, to_col_idx), ...]


@dataclass
class SpiderExample:
    """Spider 单条测试用例"""
    db_id: str
    question: str        # 自然语言问题
    gold_sql: str        # 黄金 SQL（仅用于评估，不喂给模型）
    schema: SpiderSchema


def load_tables(tables_json_path: str) -> dict[str, SpiderSchema]:
    """
    解析 tables.json，返回 dict[db_id, SpiderSchema]

    Spider tables.json 格式：
    {
        "db_id": "academic",
        "table_names_original": ["department", "head", ...],
        "column_names_original": [[-1, "*"], [0, "department_id"], ...],
        "column_types": ["text", "number", ...],
        "primary_keys": [0, 1, ...],
        "foreign_keys": [[1, 0], ...]
    }

    注意：column_names_original 的第一个元素总是 [-1, "*"]（通配符），
    实际列从索引 1 开始，column_types 也从索引 1 开始一一对应。
    """
    path = Path(tables_json_path)
    if not path.exists():
        raise FileNotFoundError(
            f"tables.json 文件不存在: {tables_json_path}\n"
            "请从 Spider 官网下载数据集: https://yale-lily.github.io/spider"
        )

    with open(path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    schemas: dict[str, SpiderSchema] = {}
    for item in raw_list:
        db_id = item["db_id"]

        # 跳过第一个通配符 [-1, "*"]，取实际列（索引 1 开始）
        raw_columns = item.get("column_names_original", item.get("column_names", []))
        raw_types = item.get("column_types", [])

        columns: list[tuple[int, str]] = []
        col_types: list[str] = []
        for (table_idx, col_name), col_type in zip(raw_columns[1:], raw_types[1:]):
            columns.append((table_idx, str(col_name)))
            col_types.append(col_type)

        schemas[db_id] = SpiderSchema(
            db_id=db_id,
            table_names=item.get("table_names_original", item.get("table_names", [])),
            column_names=columns,
            column_types=col_types,
            primary_keys=item.get("primary_keys", []),
            foreign_keys=item.get("foreign_keys", []),
        )

    return schemas


def load_examples(
    data_json_path: str,
    schemas: dict[str, SpiderSchema],
) -> list[SpiderExample]:
    """
    解析 dev.json / train_spider.json，匹配 schema

    每条记录格式：
    {
        "db_id": "academic",
        "question": "How many heads of the departments are older than 56?",
        "query": "SELECT count(*) FROM head WHERE age > 56",
        ...
    }

    返回：匹配了 schema 的 SpiderExample 列表
    如果 db_id 找不到对应 schema，跳过并打印警告
    """
    path = Path(data_json_path)
    if not path.exists():
        raise FileNotFoundError(
            f"数据文件不存在: {data_json_path}\n"
            "请从 Spider 官网下载数据集: https://yale-lily.github.io/spider"
        )

    with open(path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    examples: list[SpiderExample] = []
    skipped = 0

    for item in raw_list:
        db_id = item["db_id"]
        if db_id not in schemas:
            skipped += 1
            continue

        examples.append(SpiderExample(
            db_id=db_id,
            question=item["question"],
            gold_sql=item["query"],
            schema=schemas[db_id],
        ))

    if skipped > 0:
        print(f"[spider_loader] 警告：{skipped} 条数据的 db_id 在 tables.json 中找不到对应 schema，已跳过")

    return examples


def load_spider_data(
    data_dir: str,
    split: str = "dev",
) -> list[SpiderExample]:
    """
    加载 Spider 数据集

    参数：
        data_dir: Spider 数据根目录，包含 tables.json 和 dev.json
        split: 数据集分割，可选 "dev" / "train"

    返回：
        SpiderExample 列表
    """
    data_path = Path(data_dir)

    tables_path = data_path / "tables.json"
    if split == "dev":
        examples_path = data_path / "dev.json"
    elif split == "train":
        examples_path = data_path / "train_spider.json"
    else:
        raise ValueError(f"不支持的数据集分割: {split}，可选 'dev' / 'train'")

    schemas = load_tables(str(tables_path))
    examples = load_examples(str(examples_path), schemas)

    print(f"[spider_loader] 加载完成: {len(examples)} 条 {split} 数据, {len(schemas)} 个数据库schema")

    return examples