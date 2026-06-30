"""
BIRD 基准测试 - 数据加载模块

职责：
1. 解析 BIRD 数据格式（dev.json / train.json / mini_dev_sqlite.jsonl）
2. 加载 database_description/*.csv 获取 schema 和值描述
3. 将原始数据转换为结构化的 BirdExample / BirdSchema

支持三种数据源格式：
- 完整 BIRD：dev.json（JSON 数组）+ dev_databases/{db_id}/database_description/*.csv
- Mini-Dev V2：mini_dev_sqlite.jsonl（JSONL）+ sqlite/dev_databases/{db_id}/*.sqlite
- HuggingFace：通过 datasets 库加载

与 Spider 的关键差异：
- Schema 来自 CSV 文件（database_description/），而非集中式 tables.json
- 包含 evidence 字段（外部知识）
- 包含 difficulty 字段（难度等级）
- 黄金 SQL 字段名为 "SQL" 而非 "query"
"""

import csv
import json
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BirdSchema:
    """BIRD 数据库 Schema 定义"""
    db_id: str
    tables: list[dict] = field(default_factory=list)       # tables.csv 内容
    columns: list[dict] = field(default_factory=list)      # columns.csv 内容
    foreign_keys: list[dict] = field(default_factory=list)  # foreign_keys.csv 内容（可选）


@dataclass
class BirdExample:
    """BIRD 单条测试用例"""
    question_id: int
    db_id: str
    question: str        # 自然语言问题
    evidence: str        # 外部知识提示（BIRD 特色）
    gold_sql: str        # 黄金 SQL（仅用于评估，不喂给模型）
    difficulty: str      # 难度等级：simple / moderate / challenging
    schema: BirdSchema
    db_path: str         # SQLite 数据库文件路径


DOWNLOAD_HELP = """
数据需要单独下载，当前目录仅含代码框架，不包含数据文件。

═══ Mini-Dev（推荐，500条，~200MB） ═══
  curl -L -o /tmp/minidev.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip
  unzip /tmp/minidev.zip -d data/bird_mini_dev
  # 解压后：data/bird_mini_dev/sqlite/dev_databases/ 下有 .sqlite 文件

═══ HuggingFace（Mini-Dev，500条） ═══
  pip install datasets
  python3 -c "from datasets import load_dataset; load_dataset('birdsql/bird_mini_dev', 'mini_dev_sqlite')"

═══ 完整 BIRD Dev（12,751条，33.4GB） ═══
  curl -L -o /tmp/bird_dev.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip
  unzip /tmp/bird_dev.zip -d data/bird
  # 解压后：data/bird/dev_databases/ 下有 .sqlite 文件和 database_description/ 目录
"""


def _read_csv_robust(path: Path) -> list[dict]:
    """读取 CSV 文件，自动处理编码问题"""
    for encoding in ["utf-8-sig", "latin-1", "cp1252"]:
        try:
            with open(path, "r", encoding=encoding) as f:
                reader = csv.DictReader(f)
                return list(reader)
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _find_json_data(data_dir: Path, split: str) -> Optional[Path]:
    """
    查找 BIRD 数据文件，支持多种命名约定

    查找顺序：
    1. dev.json / train.json（完整 BIRD）
    2. mini_dev_sqlite.jsonl（Mini-Dev V2 JSONL 格式）
    3. sqlite/mini_dev_sqlite.jsonl（Mini-Dev 标准目录结构）
    """
    if split == "dev":
        candidates = [
            data_dir / "dev.json",
            data_dir / "mini_dev_sqlite.jsonl",
            data_dir / "mini_dev_sqlite.json",
            data_dir / "sqlite" / "mini_dev_sqlite.jsonl",
            data_dir / "sqlite" / "mini_dev_sqlite.json",
        ]
    elif split == "train":
        candidates = [
            data_dir / "train.json",
        ]
    else:
        raise ValueError(f"不支持的数据集分割: {split}，可选 'dev' / 'train'")

    for path in candidates:
        if path.exists():
            return path
    return None


def _find_db_dir(data_dir: Path, split: str) -> Optional[Path]:
    """
    查找数据库目录，支持多种命名约定

    查找顺序：
    1. dev_databases/ 或 train_databases/（完整 BIRD）
    2. sqlite/dev_databases/（Mini-Dev 标准结构）
    3. databases/（通用）
    """
    if split == "dev":
        candidates = [
            data_dir / "dev_databases",
            data_dir / "sqlite" / "dev_databases",
            data_dir / "databases",
        ]
    elif split == "train":
        candidates = [
            data_dir / "train_databases",
            data_dir / "databases",
        ]

    for path in candidates:
        if path.exists():
            return path
    return None


def _parse_bird_items(data_path: Path) -> list[dict]:
    """
    解析 BIRD 数据文件，自动识别 JSON 数组 / JSONL 格式

    JSON 数组格式（完整 BIRD dev.json）：
        [{"question_id": 0, "db_id": "...", "question": "...", ...}, ...]

    JSONL 格式（Mini-Dev）：
        {"question_id": 0, "db_id": "...", "question": "...", ...}
        {"question_id": 1, ...}
    """
    with open(data_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    if raw.startswith("["):
        return json.loads(raw)
    else:
        items = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                items.append(json.loads(line))
        return items


def load_database_description(db_dir: str, db_id: str) -> BirdSchema:
    """
    加载 BIRD 数据库的 schema 描述（来自 database_description/ 目录下的 CSV 文件）

    兼容两种格式：
    1. 完整版 BIRD — 聚合 CSV：
       - tables.csv:     Table Name, Description
       - columns.csv:    Table Name, Column Name, Type, Description, Sample Values
       - foreign_keys.csv（可选）

    2. Mini-Dev — 每个表一个 CSV 文件：
       - {table_name}.csv: original_column_name, column_name, column_description,
                           data_format, value_description

    返回：
        BirdSchema 对象
    """
    desc_dir = Path(db_dir) / db_id / "database_description"
    schema = BirdSchema(db_id=db_id)

    if not desc_dir.exists():
        return schema

    has_tables_csv = (desc_dir / "tables.csv").exists()
    has_columns_csv = (desc_dir / "columns.csv").exists()

    if has_tables_csv or has_columns_csv:
        # ── 完整版 BIRD 格式 ──
        if has_tables_csv:
            schema.tables = _read_csv_robust(desc_dir / "tables.csv")

        if has_columns_csv:
            schema.columns = _read_csv_robust(desc_dir / "columns.csv")

        fk_path = desc_dir / "foreign_keys.csv"
        if fk_path.exists():
            schema.foreign_keys = _read_csv_robust(fk_path)
    else:
        # ── Mini-Dev 格式：每个表一个 CSV ──
        for csv_file in sorted(desc_dir.glob("*.csv")):
            table_name = csv_file.stem
            rows = _read_csv_robust(csv_file)

            if not rows:
                continue

            schema.tables.append({
                "Table Name": table_name,
                "Description": f"Table: {table_name}",
            })

            for row in rows:
                col_name = row.get("column_name", "") or row.get("original_column_name", "")
                col_type = row.get("data_format", "")
                col_desc = row.get("column_description", "")
                col_values = row.get("value_description", "")

                schema.columns.append({
                    "Table Name": table_name,
                    "Column Name": col_name,
                    "Type": col_type,
                    "Description": col_desc,
                    "Sample Values": col_values,
                })

    return schema


def load_bird_data(
    data_dir: str,
    split: str = "dev",
    include_schema: bool = True,
) -> list[BirdExample]:
    """
    加载 BIRD 数据集

    参数：
        data_dir: BIRD 数据根目录
        split: 数据集分割，可选 "dev" / "train"
        include_schema: 是否加载 schema 描述（CSV）。设为 False 则 schema 字段为空（Agent 模式）

    返回：
        BirdExample 列表

    支持的数据目录结构：

    完整 BIRD（dev.zip 解压后）：
        data_dir/
        ├── dev.json
        └── dev_databases/
            ├── california_schools/
            │   ├── california_schools.sqlite
            │   └── database_description/
            │       ├── tables.csv
            │       └── columns.csv
            └── ...

    Mini-Dev（minidev.zip 解压后）：
        data_dir/
        ├── sqlite/
        │   ├── mini_dev_sqlite.jsonl
        │   └── dev_databases/
        │       ├── debit_card_specializing/
        │       │   └── debit_card_specializing.sqlite
        │       └── ...
    """
    data_path = Path(data_dir)

    json_path = _find_json_data(data_path, split)

    if json_path is None or not json_path.exists():
        raise FileNotFoundError(
            f"BIRD 数据文件不存在于: {data_dir}\n"
            f"期望找到: dev.json / mini_dev_sqlite.jsonl / sqlite/mini_dev_sqlite.jsonl\n"
            f"{DOWNLOAD_HELP}"
        )

    raw_items = _parse_bird_items(json_path)

    db_dir = _find_db_dir(data_path, split)

    if db_dir is None or not db_dir.exists():
        raise FileNotFoundError(
            f"BIRD 数据库目录不存在于: {data_dir}\n"
            f"期望找到: dev_databases/ / sqlite/dev_databases/ / databases/\n"
            f"{DOWNLOAD_HELP}"
        )

    examples: list[BirdExample] = []
    skipped = 0

    for item in raw_items:
        db_id = item["db_id"]
        db_path = db_dir / db_id / f"{db_id}.sqlite"

        if not db_path.exists():
            skipped += 1
            continue

        schema = BirdSchema(db_id=db_id)
        if include_schema:
            schema = load_database_description(str(db_dir), db_id)

        examples.append(BirdExample(
            question_id=item.get("question_id", 0),
            db_id=db_id,
            question=item["question"],
            evidence=item.get("evidence", ""),
            gold_sql=item["SQL"],
            difficulty=item.get("difficulty", "unknown"),
            schema=schema,
            db_path=str(db_path),
        ))

    if skipped > 0:
        print(f"[bird_loader] 警告：{skipped} 条数据的 SQLite 数据库文件不存在，已跳过")

    if len(examples) == 0:
        raise FileNotFoundError(
            "没有找到任何可用的测试数据。\n"
            f"数据文件: {json_path} (已找到，{len(raw_items)} 条记录)\n"
            f"数据库目录: {db_dir} (已找到)\n"
            "但所有条目的 .sqlite 文件都不存在，请检查数据库文件是否已正确解压。"
        )

    print(f"[bird_loader] 加载完成: {len(examples)} 条数据 "
          f"(schema={'已加载' if include_schema else '未加载-Agent模式'})")

    return examples